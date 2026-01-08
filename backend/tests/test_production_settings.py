from __future__ import annotations

from typing import Any

import pytest

from app.config import DEV_DEFAULT_JWT_SECRET, Settings


def _base_prod_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+psycopg2://rag:pass@db:5432/rag",
        "JWT_SECRET": "x" * 64,
        "GEMINI_API_KEY": "test-key-12345678901234567890",
        "REQUIRE_CSRF_HEADER": True,
        "ALLOW_DEV_LOGIN": False,
        "REQUIRE_REDIS_IN_PRODUCTION": True,
        "REDIS_URL": "redis://redis:6379/0",
    }
    kwargs.update(overrides)
    return kwargs


def test_production_happy_path_accepts_postgres_and_real_secret() -> None:
    Settings(**_base_prod_kwargs())


def test_production_disallows_sqlite_urls() -> None:
    with pytest.raises(ValueError, match="SQLite"):
        Settings(**_base_prod_kwargs(DATABASE_URL="sqlite:///./rag.db"))


def test_production_disallows_dev_jwt_secret() -> None:
    with pytest.raises(ValueError, match="Default JWT_SECRET"):
        Settings(**_base_prod_kwargs(JWT_SECRET=DEV_DEFAULT_JWT_SECRET))


def test_production_disallows_dev_login_flag() -> None:
    with pytest.raises(ValueError, match="ALLOW_DEV_LOGIN must be false"):
        Settings(**_base_prod_kwargs(ALLOW_DEV_LOGIN=True))


def test_production_requires_redis_when_flag_enabled() -> None:
    with pytest.raises(ValueError, match="REDIS_URL is required"):
        Settings(**_base_prod_kwargs(REDIS_URL=None))


def test_production_disallows_default_db_passwords() -> None:
    url = "postgresql+psycopg2://rag:localdev_password_change_in_production@db:5432/rag"
    with pytest.raises(ValueError, match="Default/blank database password"):
        Settings(**_base_prod_kwargs(DATABASE_URL=url))


def _base_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ENVIRONMENT": "development",
        "JWT_SECRET": "x" * 64,
        "GEMINI_API_KEY": "test-key-12345678901234567890",
        "DATABASE_URL": "sqlite:///./test.db",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", []),
        ("[]", []),
        ('["127.0.0.1","10.0.0.0/8"]', ["127.0.0.1/32", "10.0.0.0/8"]),
        ("127.0.0.1,10.0.0.0/8", ["127.0.0.1/32", "10.0.0.0/8"]),
    ],
)
def test_trusted_proxy_ips_parsing(value: str, expected: list[str]) -> None:
    cfg = Settings(**_base_kwargs(TRUSTED_PROXY_IPS=value))
    assert cfg.TRUSTED_PROXY_IPS == expected


@pytest.mark.parametrize("value", ["not-an-ip", "300.0.0.1", '["10.0.0.0/33"]'])
def test_trusted_proxy_ips_invalid_values_raise(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid TRUSTED_PROXY_IPS entry"):
        Settings(**_base_kwargs(TRUSTED_PROXY_IPS=value))
