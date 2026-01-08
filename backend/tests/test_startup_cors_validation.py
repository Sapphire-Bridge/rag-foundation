import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app


def test_startup_rejects_empty_cors_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "JWT_SECRET", "x" * 64)
    monkeypatch.setattr(settings, "GEMINI_MOCK_MODE", True)
    monkeypatch.setattr(settings, "ALLOW_MOCK_IN_PROD", True)
    monkeypatch.setattr(settings, "REQUIRE_REDIS_IN_PRODUCTION", False)
    monkeypatch.setattr(settings, "ALLOW_DEV_LOGIN", False)
    monkeypatch.setattr(settings, "REQUIRE_CSRF_HEADER", True)
    monkeypatch.setattr(settings, "CORS_ORIGINS", [])

    with pytest.raises(RuntimeError, match="CORS_ORIGINS must be set in staging/production"):
        with TestClient(create_app()):
            pass
