from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import User, AdminAuditLog, AppSetting

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


def test_settings_returns_defaults():
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app_name"]
    assert body["theme_preset"] == "minimal"
    assert body["app_favicon"] == ""


def test_non_admin_cannot_update_settings():
    token = _dev_token("basic-settings@example.com")
    resp = client.post(
        "/api/settings",
        json={"app_name": "New Name"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403


def test_admin_can_update_settings_and_audit_logged():
    admin_email = "admin-settings@example.com"
    token = _dev_token(admin_email)
    _promote_user(admin_email)

    resp = client.post(
        "/api/settings",
        json={
            "app_name": "Docs Copilot",
            "app_icon": "sparkles",
            "theme_preset": "gradient",
            "primary_color": "#123456",
            "app_favicon": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z/C/HwAFgwJ/lks9NwAAAABJRU5ErkJggg==",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["app_name"] == "Docs Copilot"
    assert body["theme_preset"] == "gradient"
    assert body["primary_color"] == "#123456"
    assert body["app_favicon"].startswith("data:image/png;base64,")

    session = SessionLocal()
    try:
        stored = {row.key: row.value for row in session.query(AppSetting).all()}
        assert stored["app_name"] == "Docs Copilot"
        assert stored["theme_preset"] == "gradient"
        assert stored["app_favicon"].startswith("data:image/png;base64,")
        audit_logs = session.query(AdminAuditLog).filter(AdminAuditLog.action == "update_settings").all()
        assert audit_logs, "expected audit log entry"
    finally:
        session.close()


def test_admin_rejects_oversize_favicon():
    admin_email = "admin-big-favicon@example.com"
    token = _dev_token(admin_email)
    _promote_user(admin_email)

    too_big = "data:image/png;base64," + ("A" * 200_001)
    resp = client.post(
        "/api/settings",
        json={"app_favicon": too_big},
        headers=_auth_headers(token),
    )
    assert resp.status_code in (400, 422), resp.text
