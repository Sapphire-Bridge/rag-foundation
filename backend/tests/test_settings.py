from __future__ import annotations

from app.models import User, AdminAuditLog, AppSetting


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


def test_settings_returns_defaults(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app_name"]
    assert body["theme_preset"] == "minimal"
    assert body["app_favicon"] == ""


def test_non_admin_cannot_update_settings(client):
    token = _dev_token(client, "basic-settings@example.com")
    resp = client.post(
        "/api/settings",
        json={"app_name": "New Name"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403


def test_admin_can_update_settings_and_audit_logged(client, db_session):
    admin_email = "admin-settings@example.com"
    token = _dev_token(client, admin_email)
    _promote_user(db_session, admin_email)

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

    stored = {row.key: row.value for row in db_session.query(AppSetting).all()}
    assert stored["app_name"] == "Docs Copilot"
    assert stored["theme_preset"] == "gradient"
    assert stored["app_favicon"].startswith("data:image/png;base64,")
    audit_logs = db_session.query(AdminAuditLog).filter(AdminAuditLog.action == "update_settings").all()
    assert audit_logs, "expected audit log entry"


def test_admin_rejects_oversize_favicon(client, db_session):
    admin_email = "admin-big-favicon@example.com"
    token = _dev_token(client, admin_email)
    _promote_user(db_session, admin_email)

    too_big = "data:image/png;base64," + ("A" * 200_001)
    resp = client.post(
        "/api/settings",
        json={"app_favicon": too_big},
        headers=_auth_headers(token),
    )
    assert resp.status_code in (400, 422), resp.text
