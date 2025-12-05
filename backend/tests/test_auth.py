import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import auth as auth_module


client = TestClient(app)


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


def _dev_token() -> str:
    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post("/api/auth/token", json={"email": "u@example.com"}, headers=headers)
    assert resp.status_code == 200, resp.text
    token = resp.json().get("access_token")
    assert token and isinstance(token, str)
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def test_dev_login_token():
    """Use dev token flow in tests to avoid password/CSRF complexity."""
    tok = _dev_token()
    assert isinstance(tok, str) and len(tok) > 10


def test_token_valid_before_revocation():
    """Issued tokens should work until explicitly revoked."""
    tok = _dev_token()
    resp = client.get("/api/stores", headers=_auth_headers(tok))
    assert resp.status_code == 200, resp.text


def test_revoked_token_is_rejected():
    """Once logout runs, the same JWT should be rejected on future calls."""
    tok = _dev_token()
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
