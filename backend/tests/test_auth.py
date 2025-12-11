import pytest
from app import auth as auth_module
from app.models import User


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        # Ignore TTL in tests; Redis returns True-y acknowledgement
        if ttl > 0:
            self.store[key] = value

    def exists(self, key: str) -> int:
        return 1 if key in self.store else 0


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Simulate Redis for JWT revocation tests without a running server."""
    fake = _FakeRedis()
    monkeypatch.setattr(auth_module, "_rev", fake, raising=False)
    yield fake


def _dev_token(client) -> str:
    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post("/api/auth/token", json={"email": "u@example.com"}, headers=headers)
    assert resp.status_code == 200, resp.text
    token = resp.json().get("access_token")
    assert token and isinstance(token, str)
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def test_dev_login_token(client):
    """Use dev token flow in tests to avoid password/CSRF complexity."""
    tok = _dev_token(client)
    assert isinstance(tok, str) and len(tok) > 10


def test_token_valid_before_revocation(client):
    """Issued tokens should work until explicitly revoked."""
    tok = _dev_token(client)
    resp = client.get("/api/stores", headers=_auth_headers(tok))
    assert resp.status_code == 200, resp.text


def test_revoked_token_is_rejected(client):
    """Once logout runs, the same JWT should be rejected on future calls."""
    tok = _dev_token(client)
    headers = _auth_headers(tok)

    # Initial call succeeds
    resp_ok = client.get("/api/stores", headers=headers)
    assert resp_ok.status_code == 200, resp_ok.text

    # Logout should revoke the token
    resp_logout = client.post("/api/auth/logout", headers=headers)
    assert resp_logout.status_code == 200, resp_logout.text

    # Subsequent call is now unauthorized
    resp_revoked = client.get("/api/stores", headers=headers)
    assert resp_revoked.status_code == 401


def test_inactive_user_is_rejected(client, db_session):
    tok = _dev_token(client)
    headers = _auth_headers(tok)
    user = db_session.query(User).filter(User.email == "u@example.com").one()
    user.is_active = False
    db_session.commit()

    resp = client.get("/api/stores", headers=headers)
    assert resp.status_code == 403

    # Restore active flag for any further operations within the same session
    user.is_active = True
    db_session.commit()
