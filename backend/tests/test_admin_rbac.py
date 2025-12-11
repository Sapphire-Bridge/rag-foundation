from __future__ import annotations

import datetime

from app.models import User, Store, Document, DocumentStatus, AdminAuditLog


def _dev_token(client, email: str) -> str:
    resp = client.post("/api/auth/token", json={"email": email}, headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def _promote_user(session, email: str) -> None:
    user = session.query(User).filter(User.email == email.lower()).one()
    user.is_admin = True
    session.commit()


def test_non_admin_cannot_access_admin_routes(client):
    token = _dev_token(client, "basic@example.com")
    resp = client.get("/api/admin/users", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_admin_can_toggle_roles_and_logs_action(client, db_session):
    admin_email = "admin-role@example.com"
    target_email = "target-role@example.com"
    admin_token = _dev_token(client, admin_email)
    _promote_user(db_session, admin_email)
    _ = _dev_token(client, target_email)

    target = db_session.query(User).filter(User.email == target_email).one()

    resp = client.post(
        f"/api/admin/users/{target.id}/role",
        json={"is_admin": True},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_admin"] is True

    logs = (
        db_session.query(AdminAuditLog)
        .filter(AdminAuditLog.action == "set_user_role", AdminAuditLog.target_id == str(target.id))
        .all()
    )
    assert logs, "expected admin audit log for role change"


def test_admin_watchdog_resets_documents(client, db_session):
    admin_email = "admin-watchdog@example.com"
    admin_token = _dev_token(client, admin_email)
    _promote_user(db_session, admin_email)

    admin_user = db_session.query(User).filter(User.email == admin_email).one()
    store = Store(user_id=admin_user.id, display_name="Admin Store", fs_name="stores/admin-watchdog")
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)

    doc = Document(
        store_id=store.id,
        filename="stuck.pdf",
        display_name="stuck",
        size_bytes=10,
        status=DocumentStatus.RUNNING,
        created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    doc_id = doc.id

    resp = client.post(
        "/api/admin/watchdog/reset-stuck",
        json={"ttl_minutes": 10},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reset_count"] >= 1

    db_session.expire_all()
    updated = db_session.get(Document, doc_id)
    assert updated.status == DocumentStatus.PENDING
