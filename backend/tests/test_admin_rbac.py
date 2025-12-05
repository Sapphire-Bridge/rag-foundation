from __future__ import annotations

import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import User, Store, Document, DocumentStatus, AdminAuditLog


client = TestClient(app)


def _dev_token(email: str) -> str:
    resp = client.post("/api/auth/token", json={"email": email}, headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def _promote_user(email: str) -> None:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == email.lower()).one()
        user.is_admin = True
        session.commit()
    finally:
        session.close()


def test_non_admin_cannot_access_admin_routes():
    token = _dev_token("basic@example.com")
    resp = client.get("/api/admin/users", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_admin_can_toggle_roles_and_logs_action():
    admin_email = "admin-role@example.com"
    target_email = "target-role@example.com"
    admin_token = _dev_token(admin_email)
    _promote_user(admin_email)
    _ = _dev_token(target_email)

    session = SessionLocal()
    target = session.query(User).filter(User.email == target_email).one()
    session.close()

    resp = client.post(
        f"/api/admin/users/{target.id}/role",
        json={"is_admin": True},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_admin"] is True

    session = SessionLocal()
    logs = (
        session.query(AdminAuditLog)
        .filter(AdminAuditLog.action == "set_user_role", AdminAuditLog.target_id == str(target.id))
        .all()
    )
    session.close()
    assert logs, "expected admin audit log for role change"


def test_admin_watchdog_resets_documents():
    admin_email = "admin-watchdog@example.com"
    admin_token = _dev_token(admin_email)
    _promote_user(admin_email)

    session = SessionLocal()
    try:
        admin_user = session.query(User).filter(User.email == admin_email).one()
        store = Store(user_id=admin_user.id, display_name="Admin Store", fs_name="stores/admin-watchdog")
        session.add(store)
        session.commit()
        session.refresh(store)

        doc = Document(
            store_id=store.id,
            filename="stuck.pdf",
            display_name="stuck",
            size_bytes=10,
            status=DocumentStatus.RUNNING,
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        doc_id = doc.id
    finally:
        session.close()

    resp = client.post(
        "/api/admin/watchdog/reset-stuck",
        json={"ttl_minutes": 10},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reset_count"] >= 1

    session = SessionLocal()
    try:
        updated = session.get(Document, doc_id)
        assert updated.status == DocumentStatus.PENDING
    finally:
        session.close()
