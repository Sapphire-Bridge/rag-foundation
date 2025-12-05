import json
import logging
from unittest.mock import MagicMock, Mock, patch

from fastapi.testclient import TestClient

from app.auth import get_authorization as real_get_authorization
from app.auth import get_current_user as real_get_current_user
from app.db import get_db as real_get_db
import app.routes.chat as chat_routes
from app.main import app


def _record_payload(record):
    if isinstance(record.msg, dict):
        return record.msg
    try:
        return json.loads(record.getMessage())
    except Exception:
        return None


def test_request_headers_are_scrubbed(caplog):
    client = TestClient(app)
    secret = "super-secret-token"
    with caplog.at_level(logging.INFO):
        response = client.get(
            "/health",
            headers={
                "Authorization": f"Bearer {secret}",
                "Cookie": "session=abc",
                "X-API-Key": "key-123",
            },
        )

    assert response.status_code in (200, 503)

    found = False
    for record in caplog.records:
        payload = _record_payload(record)
        if not isinstance(payload, dict) or payload.get("event") != "request_complete":
            continue
        found = True
        headers = payload.get("request_headers") or {}
        assert headers.get("authorization") == "[REDACTED]"
        assert headers.get("cookie") == "[REDACTED]"
        assert headers.get("x-api-key") == "[REDACTED]"
        assert secret not in json.dumps(headers)
    assert found
    assert secret not in caplog.text


def test_llm_errors_are_redacted(caplog):
    client = TestClient(app)
    mock_user = Mock(id=1)
    app.dependency_overrides[real_get_current_user] = lambda: mock_user
    app.dependency_overrides[real_get_authorization] = lambda: "test-token"
    app.dependency_overrides[chat_routes.get_authorization] = lambda: "test-token"
    orig_get_current_user = chat_routes.get_current_user
    orig_session_local = chat_routes.SessionLocal
    chat_routes.get_current_user = lambda db, token: mock_user
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.one_or_none.return_value = None
    chat_routes.SessionLocal = lambda: mock_db

    def _ov_db():
        yield mock_db

    app.dependency_overrides[real_get_db] = _ov_db

    secret_prompt = "never log this prompt text"
    mock_store = Mock(id=1, fs_name="test-store", user_id=mock_user.id)
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

    class NoisyLLMError(Exception):
        def __init__(self, message, code=None):
            super().__init__(message)
            self.code = code

    noisy_error = NoisyLLMError(f"LLM saw: {secret_prompt}", code=503)

    response = None
    try:
        with (
            patch("app.routes.chat.user_budget", return_value=None),
            patch("app.routes.chat.mtd_spend", return_value=0),
        ):
            with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                mock_rag = MagicMock()
                mock_rag_client.return_value = mock_rag
                mock_rag.new_stream_ids.return_value = ("msg-err", "text-err")
                mock_rag.ask_stream.side_effect = noisy_error
                mock_rag.extract_citations_from_response.return_value = []

                with caplog.at_level(logging.INFO):
                    response = client.post(
                        "/api/chat",
                        json={"question": secret_prompt, "storeIds": [1], "model": "gemini-2.5-flash"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )
    finally:
        chat_routes.get_current_user = orig_get_current_user
        chat_routes.SessionLocal = orig_session_local
        app.dependency_overrides.pop(real_get_current_user, None)
        app.dependency_overrides.pop(real_get_authorization, None)
        app.dependency_overrides.pop(chat_routes.get_authorization, None)
        app.dependency_overrides.pop(real_get_db, None)

    assert response is not None
    assert response.status_code == 200
    assert "error" in response.text

    redaction_logged = False
    for record in caplog.records:
        payload = _record_payload(record)
        if not isinstance(payload, dict):
            continue
        if payload.get("event") in {"chat_stream_exception", "chat_stream_failed"}:
            redaction_logged = True
            serialized = json.dumps(payload)
            assert secret_prompt not in serialized
            assert payload.get("detail") == "[REDACTED]"
    assert redaction_logged
    assert secret_prompt not in caplog.text
