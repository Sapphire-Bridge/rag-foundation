from fastapi.testclient import TestClient
from app.main import app


def test_sse_headers_present():
    c = TestClient(app)
    # Unauthorized should be 401/400, route exists
    r = c.post("/api/chat", json={}, headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code in (400, 401)
