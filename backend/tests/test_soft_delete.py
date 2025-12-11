from __future__ import annotations

import io

from app.models import Document, DocumentStatus, User


def _dev_token(client, email: str = "soft-delete@example.com") -> str:
    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post("/api/auth/token", json={"email": email}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _promote_to_admin(session, email: str) -> None:
    """Helper for tests: mark a user as admin directly in the DB."""
    user = session.query(User).filter(User.email == email).one_or_none()
    if user:
        user.is_admin = True
        session.commit()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def _create_store(client, token: str, display_name: str = "Soft Delete Store") -> int:
    resp = client.post("/api/stores", json={"display_name": display_name}, headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_delete_store_hides_from_listing(client):
    token = _dev_token(client, "store-delete@example.com")
    store_id = _create_store(client, token)

    resp = client.delete(f"/api/stores/{store_id}", headers=_auth_headers(token))
    assert resp.status_code == 202, resp.text

    resp = client.get("/api/stores", headers=_auth_headers(token))
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert store_id not in ids


def test_upload_blocked_once_store_deleted(client):
    token = _dev_token(client, "store-upload-block@example.com")
    store_id = _create_store(client, token)

    # Delete store first
    resp = client.delete(f"/api/stores/{store_id}", headers=_auth_headers(token))
    assert resp.status_code == 202

    files = {"file": ("file.pdf", io.BytesIO(b"%PDF-1.4 test %%EOF"), "application/pdf")}
    data = {"storeId": str(store_id)}
    resp = client.post("/api/upload", data=data, files=files, headers=_auth_headers(token))
    assert resp.status_code == 404


def test_document_delete_and_restore_round_trip(client, db_session):
    email = "doc-delete@example.com"
    token = _dev_token(client, email)
    _promote_to_admin(db_session, email)
    store_id = _create_store(client, token)

    # Insert document directly to avoid running upload pipeline
    doc = Document(
        store_id=store_id,
        filename="doc.pdf",
        display_name="Doc",
        size_bytes=123,
        status=DocumentStatus.PENDING,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    doc_id = doc.id

    resp = client.delete(f"/api/documents/{doc_id}", headers=_auth_headers(token))
    assert resp.status_code == 202, resp.text

    # Refresh state from the database; another session performed the update
    db_session.expire_all()
    deleted = db_session.get(Document, doc_id)
    assert deleted and deleted.deleted_at is not None

    resp = client.post(f"/api/documents/{doc_id}/restore", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    restored = db_session.get(Document, doc_id)
    assert restored and restored.deleted_at is None


def test_store_restore_makes_store_visible_again(client, db_session):
    email = "store-restore@example.com"
    token = _dev_token(client, email)
    _promote_to_admin(db_session, email)
    store_id = _create_store(client, token)

    resp = client.delete(f"/api/stores/{store_id}", headers=_auth_headers(token))
    assert resp.status_code == 202

    resp = client.post(f"/api/stores/{store_id}/restore", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text

    resp = client.get("/api/stores", headers=_auth_headers(token))
    assert any(row["id"] == store_id for row in resp.json())
