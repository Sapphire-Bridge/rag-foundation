from __future__ import annotations

import io
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Document, DocumentStatus, User


client = TestClient(app)


def _dev_token(email: str = "soft-delete@example.com") -> str:
    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post("/api/auth/token", json={"email": email}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _promote_to_admin(email: str) -> None:
    """Helper for tests: mark a user as admin directly in the DB."""
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == email).one_or_none()
        if user:
            user.is_admin = True
            session.commit()
    finally:
        session.close()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def _create_store(token: str, display_name: str = "Soft Delete Store") -> int:
    resp = client.post("/api/stores", json={"display_name": display_name}, headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_delete_store_hides_from_listing():
    token = _dev_token("store-delete@example.com")
    store_id = _create_store(token)

    resp = client.delete(f"/api/stores/{store_id}", headers=_auth_headers(token))
    assert resp.status_code == 202, resp.text

    resp = client.get("/api/stores", headers=_auth_headers(token))
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert store_id not in ids


def test_upload_blocked_once_store_deleted():
    token = _dev_token("store-upload-block@example.com")
    store_id = _create_store(token)

    # Delete store first
    resp = client.delete(f"/api/stores/{store_id}", headers=_auth_headers(token))
    assert resp.status_code == 202

    files = {"file": ("file.pdf", io.BytesIO(b"%PDF-1.4 test %%EOF"), "application/pdf")}
    data = {"storeId": str(store_id)}
    resp = client.post("/api/upload", data=data, files=files, headers=_auth_headers(token))
    assert resp.status_code == 404


def test_document_delete_and_restore_round_trip():
    email = "doc-delete@example.com"
    token = _dev_token(email)
    _promote_to_admin(email)
    store_id = _create_store(token)

    # Insert document directly to avoid running upload pipeline
    session = SessionLocal()
    try:
        doc = Document(
            store_id=store_id,
            filename="doc.pdf",
            display_name="Doc",
            size_bytes=123,
            status=DocumentStatus.PENDING,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        doc_id = doc.id
    finally:
        session.close()
    resp = client.delete(f"/api/documents/{doc_id}", headers=_auth_headers(token))
    assert resp.status_code == 202, resp.text

    # Verify soft delete flag persisted
    session = SessionLocal()
    try:
        deleted = session.get(Document, doc_id)
        assert deleted and deleted.deleted_at is not None
    finally:
        session.close()

    resp = client.post(f"/api/documents/{doc_id}/restore", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text

    session = SessionLocal()
    try:
        restored = session.get(Document, doc_id)
        assert restored and restored.deleted_at is None
    finally:
        session.close()


def test_store_restore_makes_store_visible_again():
    email = "store-restore@example.com"
    token = _dev_token(email)
    _promote_to_admin(email)
    store_id = _create_store(token)

    resp = client.delete(f"/api/stores/{store_id}", headers=_auth_headers(token))
    assert resp.status_code == 202

    resp = client.post(f"/api/stores/{store_id}/restore", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text

    resp = client.get("/api/stores", headers=_auth_headers(token))
    assert any(row["id"] == store_id for row in resp.json())
