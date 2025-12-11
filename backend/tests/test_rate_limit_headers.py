from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.rate_limit import limiter


def test_429_carries_request_id():
    client = TestClient(app, raise_server_exceptions=False)
    original_limit = settings.RATE_LIMIT_PER_MINUTE
    # Reset in-memory limiter state to avoid bleed between tests
    limiter._memory_limiter.store.clear()
    limiter._memory_limiter.last_seen.clear()
    try:
        settings.RATE_LIMIT_PER_MINUTE = 1
        client.get("/health")
        resp = client.get("/health")
        assert resp.status_code == 429
        assert resp.headers.get("X-Request-ID")
    finally:
        settings.RATE_LIMIT_PER_MINUTE = original_limit
        limiter._memory_limiter.store.clear()
        limiter._memory_limiter.last_seen.clear()
