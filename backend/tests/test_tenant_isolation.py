from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

from app.auth import get_current_user
from app.models import Document, Store, DocumentStatus, User
import app.routes.chat as chat_routes


def _headers():
    return {"Authorization": "Bearer test", "X-Requested-With": "XMLHttpRequest"}


def _create_store(db_session, user_id: int) -> Store:
    # Ensure the owning user exists to satisfy FK constraints
    user = db_session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            email=f"user-{user_id}@example.com",
            hashed_password="",
            is_active=True,
            email_verified=True,
            is_admin=False,
        )
        db_session.add(user)
        db_session.commit()

    store = Store(
        user_id=user_id,
        display_name="Tenant Store",
        fs_name=f"stores/test-{uuid.uuid4().hex}",
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


def test_upload_rejects_other_users_store(client, db_session):
    attacker = SimpleNamespace(id=200)
    client.app.dependency_overrides[get_current_user] = lambda: attacker
    victim_store = _create_store(db_session, user_id=999)
    try:
        resp = client.post(
            "/api/upload",
            data={"storeId": str(victim_store.id)},
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 404
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_document_ops_enforce_tenant(client, db_session):
    attacker = SimpleNamespace(id=202)
    client.app.dependency_overrides[get_current_user] = lambda: attacker
    victim_store = _create_store(db_session, user_id=321)
    try:
        doc = Document(
            store_id=victim_store.id,
            filename="file.txt",
            display_name="file.txt",
            size_bytes=10,
            status=DocumentStatus.PENDING,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        resp = client.get(f"/api/upload/op-status/doc-{doc.id}", headers=_headers())
        assert resp.status_code == 404
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_chat_rejects_other_users_store(client, db_session):
    attacker = SimpleNamespace(id=201)
    client.app.dependency_overrides[get_current_user] = lambda: attacker
    orig_get_current_user = chat_routes.get_current_user
    chat_routes.get_current_user = lambda db, token: attacker
    victim_store = _create_store(db_session, user_id=1234)
    try:
        resp = client.post(
            "/api/chat",
            json={
                "storeIds": [victim_store.id],
                "question": "Hello?",
            },
            headers=_headers(),
        )
        assert resp.status_code == 404
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)
        chat_routes.get_current_user = orig_get_current_user
