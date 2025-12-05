from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import ChatHistory, Store
from app.routes import chat as chat_routes


def _mk_store(user_id: int) -> Store:
    session = SessionLocal()
    store = Store(
        user_id=user_id,
        display_name="Test Store",
        fs_name=f"stores/test-{uuid.uuid4().hex}",
    )
    session.add(store)
    session.commit()
    session.refresh(store)
    session.close()
    return store


def _cleanup_store(store_id: int) -> None:
    session = SessionLocal()
    try:
        session.query(ChatHistory).filter(ChatHistory.store_id == store_id).delete()
        store = session.get(Store, store_id)
        if store:
            session.delete(store)
        session.commit()
    finally:
        session.close()


def test_load_chat_history_filters_by_store():
    session = SessionLocal()
    store_a = _mk_store(user_id=1)
    store_b = _mk_store(user_id=1)
    try:
        session.add(
            ChatHistory(
                user_id=1,
                store_id=store_a.id,
                session_id="thread-1",
                role="user",
                content="from store A",
            )
        )
        session.add(
            ChatHistory(
                user_id=1,
                store_id=store_b.id,
                session_id="thread-1",
                role="assistant",
                content="from store B",
            )
        )
        session.commit()

        rows = chat_routes._load_chat_history(session, user_id=1, session_id="thread-1", store_id=store_a.id)
        assert rows
        assert {row.store_id for row in rows} == {store_a.id}
        assert [row.content for row in rows] == ["from store A"]
    finally:
        session.query(ChatHistory).filter(ChatHistory.session_id == "thread-1", ChatHistory.user_id == 1).delete()
        session.commit()
        session.close()
        _cleanup_store(store_a.id)
        _cleanup_store(store_b.id)


def test_chat_rejects_oversize_question():
    client = TestClient(app)
    store = _mk_store(user_id=9999)
    from app.auth import get_authorization as real_get_authorization

    # Bypass auth/CSRF in tests while keeping route logic intact
    app.dependency_overrides[real_get_authorization] = lambda: "test-token"
    orig_get_current_user = chat_routes.get_current_user
    chat_routes.get_current_user = lambda db, token: SimpleNamespace(id=store.user_id)
    try:
        resp = client.post(
            "/api/chat",
            json={
                "storeIds": [store.id],
                "question": "x" * (chat_routes.MAX_QUESTION_LENGTH + 1),
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
        )
        assert resp.status_code == 400
        assert "Question too long" in resp.json().get("detail", "")
    finally:
        app.dependency_overrides.pop(real_get_authorization, None)
        chat_routes.get_current_user = orig_get_current_user
        _cleanup_store(store.id)
