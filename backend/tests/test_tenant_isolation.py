from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.db import SessionLocal
from app.main import app
from app.models import Document, Store, DocumentStatus
import app.routes.chat as chat_routes


@pytest.fixture()
def client():
    return TestClient(app)


def _headers():
    return {"Authorization": "Bearer test", "X-Requested-With": "XMLHttpRequest"}


def _create_store(user_id: int) -> Store:
    session = SessionLocal()
    store = Store(
        user_id=user_id,
        display_name="Tenant Store",
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
        store = session.get(Store, store_id)
        if store:
            session.query(Document).filter(Document.store_id == store_id).delete()
            session.delete(store)
            session.commit()
    finally:
        session.close()


def test_upload_rejects_other_users_store(client):
    attacker = SimpleNamespace(id=200)
    app.dependency_overrides[get_current_user] = lambda: attacker
    victim_store = _create_store(user_id=999)
    try:
        resp = client.post(
            "/api/upload",
            data={"storeId": str(victim_store.id)},
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _cleanup_store(victim_store.id)


def test_document_ops_enforce_tenant(client):
    attacker = SimpleNamespace(id=202)
    app.dependency_overrides[get_current_user] = lambda: attacker
    victim_store = _create_store(user_id=321)
    session = SessionLocal()
    try:
        doc = Document(
            store_id=victim_store.id,
            filename="file.txt",
            display_name="file.txt",
            size_bytes=10,
            status=DocumentStatus.PENDING,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        resp = client.get(f"/api/upload/op-status/doc-{doc.id}", headers=_headers())
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        session.close()
        _cleanup_store(victim_store.id)


def test_chat_rejects_other_users_store(client):
    attacker = SimpleNamespace(id=201)
    app.dependency_overrides[get_current_user] = lambda: attacker
    orig_get_current_user = chat_routes.get_current_user
    chat_routes.get_current_user = lambda db, token: attacker
    victim_store = _create_store(user_id=1234)
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
        app.dependency_overrides.pop(get_current_user, None)
        chat_routes.get_current_user = orig_get_current_user
        _cleanup_store(victim_store.id)
