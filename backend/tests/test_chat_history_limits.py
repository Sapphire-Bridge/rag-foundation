from __future__ import annotations

import uuid
from fastapi import Depends
from sqlalchemy.orm import Session

from app.models import ChatHistory, Store, User
from app.routes import chat as chat_routes


def _mk_store(db_session, user_id: int) -> Store:
    # Ensure owning user exists for FK integrity
    user = db_session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            email=f"user-{user_id}@example.com",
            hashed_password="",
            is_active=True,
            email_verified=True,
        )
        db_session.add(user)
        db_session.commit()

    store = Store(
        user_id=user_id,
        display_name="Test Store",
        fs_name=f"stores/test-{uuid.uuid4().hex}",
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


def test_load_chat_history_filters_by_store(db_session):
    store_a = _mk_store(db_session, user_id=1)
    store_b = _mk_store(db_session, user_id=1)

    # ChatHistory rows require a ChatSession FK
    from app.models import ChatSession

    session_row = ChatSession(id="thread-1", user_id=1, store_id=store_a.id)
    db_session.add(session_row)
    db_session.commit()

    db_session.add(
        ChatHistory(
            user_id=1,
            store_id=store_a.id,
            session_id="thread-1",
            role="user",
            content="from store A",
        )
    )
    db_session.add(
        ChatHistory(
            user_id=1,
            store_id=store_b.id,
            session_id="thread-1",
            role="assistant",
            content="from store B",
        )
    )
    db_session.commit()

    rows = chat_routes._load_chat_history(db_session, user_id=1, session_id="thread-1", store_id=store_a.id)
    assert rows
    assert {row.store_id for row in rows} == {store_a.id}
    assert [row.content for row in rows] == ["from store A"]


def test_chat_rejects_oversize_question(client, db_session):
    store = _mk_store(db_session, user_id=9999)
    from app.auth import get_authorization as real_get_authorization

    # Bypass auth/CSRF in tests while keeping route logic intact
    client.app.dependency_overrides[real_get_authorization] = lambda: "test-token"
    orig_get_current_user = chat_routes.get_current_user
    user = User(
        id=store.user_id,
        email=f"user-{store.user_id}@example.com",
        hashed_password="",
        is_active=True,
        email_verified=True,
        is_admin=False,
    )

    def _ov_get_current_user(
        db: Session = Depends(chat_routes.get_db),
        token: str = Depends(chat_routes.get_authorization),
    ) -> User:
        return user

    chat_routes.get_current_user = _ov_get_current_user
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
        client.app.dependency_overrides.pop(real_get_authorization, None)
        chat_routes.get_current_user = orig_get_current_user
