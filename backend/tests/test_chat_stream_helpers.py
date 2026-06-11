from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

from app.models import ChatHistory, ChatSession, QueryLog, User
from app.routes import chat as chat_routes


def _payload(frame: str) -> dict:
    assert frame.startswith("data: ")
    return json.loads(frame.removeprefix("data: ").strip())


def test_mark_error_records_state_and_retry_hint():
    state = chat_routes._StreamState(last_send=0)

    frame = chat_routes._mark_error(
        state,
        "stream_backpressure",
        "Client too slow to receive stream. Please retry.",
        503,
        retry_after_ms=250,
    )

    payload = _payload(frame)
    assert state.error_sent is True
    assert state.last_error_code == "stream_backpressure"
    assert state.last_error_message == "Client too slow to receive stream. Please retry."
    assert payload["type"] == "error"
    assert payload["code"] == "stream_backpressure"
    assert payload["status"] == 503
    assert payload["retryAfterMs"] == 250


def test_citation_frames_preserve_source_document_wire_format():
    rag = SimpleNamespace(
        extract_citations_from_response=lambda _resp: [
            {
                "index": 3,
                "title": "Source title",
                "uri": "mock://source",
                "snippet": "Relevant excerpt",
            }
        ]
    )

    frames = list(chat_routes._citation_frames(rag, object()))

    assert len(frames) == 1
    payload = _payload(frames[0])
    assert payload == {
        "type": "source-document",
        "sourceId": "cit-3",
        "mediaType": "file",
        "title": "Source title",
        "snippet": "Relevant excerpt",
    }


def test_finish_frame_exposes_frontend_usage_contract():
    frame = chat_routes._finish_frame(prompt_tokens=12, completion_tokens=8, model="gemini-2.5-flash")

    payload = _payload(frame)

    assert payload["type"] == "finish"
    assert payload["finishReason"] == "stop"
    assert payload["promptTokens"] == 12
    assert payload["completionTokens"] == 8
    assert payload["usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "model": "gemini-2.5-flash",
    }


def test_resolve_final_usage_prefers_sdk_usage_metadata(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(chat_routes, "log_json", lambda *args, **kwargs: calls.append((args, kwargs)))
    final_resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count="11",
            candidates_token_count="4",
        )
    )

    prompt_tokens, completion_tokens = chat_routes._resolve_final_usage(
        final_resp,
        prompt_tokens_est=7,
        completion_tokens_est=2,
        assistant_text_parts=["ignored"],
        user_id=1,
        model="gemini-2.5-flash",
    )

    assert (prompt_tokens, completion_tokens) == (11, 4)
    assert calls == []


def test_resolve_final_usage_falls_back_to_local_estimate(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(chat_routes, "log_json", lambda *args, **kwargs: calls.append((args, kwargs)))

    prompt_tokens, completion_tokens = chat_routes._resolve_final_usage(
        None,
        prompt_tokens_est=7,
        completion_tokens_est=0,
        assistant_text_parts=["hello world"],
        user_id=1,
        model="gemini-2.5-flash",
    )

    assert prompt_tokens == 7
    assert completion_tokens == chat_routes._estimate_tokens_from_text("hello world")
    assert calls
    assert calls[0][0][1] == "chat_usage_metadata_missing"


def test_finalize_and_persist_records_query_and_assistant_message(session_factory, db_session):
    user = User(
        id=123,
        email="stream-helper@example.com",
        hashed_password="",
        is_active=True,
        email_verified=True,
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()

    session = ChatSession(id="helper-session", user_id=user.id, store_id=None, title="Helper test")
    db_session.add(session)
    db_session.commit()

    result = chat_routes._finalize_and_persist(
        session_factory,
        user_id=user.id,
        store_id_for_cost=None,
        store_id_for_history=None,
        session_id=session.id,
        model="gemini-2.5-flash",
        project_id=44,
        tags={"suite": "stream-helper"},
        final_resp=SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=8)),
        prompt_tokens_est=1,
        completion_tokens_est=1,
        assistant_text_parts=["assistant reply"],
    )

    db_session.expire_all()
    query_log = db_session.query(QueryLog).filter(QueryLog.user_id == user.id).one()
    message = db_session.query(ChatHistory).filter(ChatHistory.session_id == session.id).one()

    assert result.prompt_tokens == 12
    assert result.completion_tokens == 8
    assert result.cost_result.total_cost_usd > Decimal("0")
    assert result.over_budget is False
    assert query_log.project_id == 44
    assert query_log.tags == {"suite": "stream-helper"}
    assert message.role == "assistant"
    assert message.content == "assistant reply"
