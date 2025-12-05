from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_metrics_endpoint_allows_when_enabled():
    client = TestClient(app)
    original = settings.METRICS_ALLOW_ALL
    settings.METRICS_ALLOW_ALL = True
    try:
        resp = client.get("/metrics")
    finally:
        settings.METRICS_ALLOW_ALL = original

    assert resp.status_code == 200
    assert b"# HELP" in resp.content
