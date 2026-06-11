from types import SimpleNamespace

import httpx

import app.main as main_module
from app.config import settings


def test_live_endpoint_reports_process_liveness(client):
    response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint_reports_local_dependencies(client, monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", None)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"database": True, "redis": True}


def test_health_gemini_probe_sends_api_key_in_header_not_url(client, monkeypatch):
    fake_key = "AIzaSyFakeSecretForHealthProbe"
    seen: dict[str, object] = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers")
        seen["params"] = kwargs.get("params")
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(settings, "GEMINI_MOCK_MODE", False)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", fake_key)
    monkeypatch.setattr(settings, "REDIS_URL", None)
    monkeypatch.setattr(main_module, "ping_db", lambda: True)
    monkeypatch.setattr(main_module, "get_rag_client", lambda: SimpleNamespace(is_mock=False))
    monkeypatch.setattr(httpx, "get", fake_get)
    main_module._gemini_health_cache["ts"] = 0.0
    main_module._gemini_health_cache["ok"] = False

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"database": True, "gemini_api": True, "redis": True}
    assert "key=" not in str(seen["url"])
    assert fake_key not in str(seen["url"])
    assert seen["params"] == {"pageSize": 1}
    assert seen["headers"] == {"x-goog-api-key": fake_key}
