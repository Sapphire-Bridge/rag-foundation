import json
import os
import subprocess
import sys
from pathlib import Path


def _run_python(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        env=full_env,
    )


def _last_json_line(output: str) -> dict:
    lines = [ln for ln in output.splitlines() if ln.strip()]
    return json.loads(lines[-1])


def _base_env(**overrides: str) -> dict[str, str]:
    env = {
        "ENVIRONMENT": "development",
        "JWT_SECRET": "x" * 64,
        "GEMINI_API_KEY": "test-api-key-1234567890",
        "DATABASE_URL": f"sqlite:///{Path.cwd() / 'test-defaults.db'}",
        "GEMINI_MOCK_MODE": "true",
        "ALLOW_DEV_LOGIN": "false",
        "REQUIRE_CSRF_HEADER": "true",
    }
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env


def _matrix_script() -> str:
    return """
import json
from fastapi.testclient import TestClient
from app.db import engine
from app.models import Base
from app.main import create_app

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(create_app())
resp_token = client.post(
    "/api/auth/token",
    json={"email": "u@example.com"},
    headers={"X-Requested-With": "XMLHttpRequest"},
)
resp_no_csrf = client.post("/api/stores", json={"display_name": "CSRF Test"})
resp_with_csrf = client.post(
    "/api/stores",
    json={"display_name": "CSRF Test"},
    headers={"X-Requested-With": "XMLHttpRequest"},
)

print(json.dumps({
    "token_status": resp_token.status_code,
    "csrf_missing_status": resp_no_csrf.status_code,
    "csrf_with_header_status": resp_with_csrf.status_code,
}))
"""


def _startup_script() -> str:
    return """
import json
from fastapi.testclient import TestClient
from app.main import create_app

result = {"ok": True, "error": None}
try:
    client = TestClient(create_app())
    client.get("/health")
except Exception as exc:
    result["ok"] = False
    result["error"] = str(exc)

print(json.dumps(result))
"""


def _run_startup(env: dict[str, str]) -> dict:
    result = _run_python(_startup_script(), env)
    if result.returncode != 0:
        # Validation failures now occur during settings load; return structured failure.
        return {"ok": False, "error": (result.stderr or "").strip() or result.stdout.strip()}
    return _last_json_line(result.stdout)


def test_default_env_disables_dev_login_and_requires_csrf() -> None:
    result = _run_python(_matrix_script(), _base_env())
    assert result.returncode == 0, result.stderr

    payload = _last_json_line(result.stdout)
    assert payload["token_status"] in (404, 405), payload  # endpoint not mounted
    assert payload["csrf_missing_status"] == 403, payload
    assert payload["csrf_with_header_status"] != 403, payload


def test_dev_env_allows_dev_login_when_opted_in() -> None:
    env = _base_env(ALLOW_DEV_LOGIN="true")
    result = _run_python(_matrix_script(), env)
    assert result.returncode == 0, result.stderr

    payload = _last_json_line(result.stdout)
    assert payload["token_status"] == 200, payload
    assert payload["csrf_missing_status"] == 403, payload
    assert payload["csrf_with_header_status"] != 403, payload


def test_csrf_can_be_disabled_explicitly() -> None:
    env = _base_env(REQUIRE_CSRF_HEADER="false", ALLOW_DEV_LOGIN="true")
    result = _run_python(_matrix_script(), env)
    assert result.returncode == 0, result.stderr

    payload = _last_json_line(result.stdout)
    assert payload["token_status"] == 200, payload
    # When CSRF disabled, middleware should not block; auth may still reject
    assert payload["csrf_missing_status"] != 403, payload
    assert payload["csrf_with_header_status"] != 403, payload


def test_production_rejects_dev_login_on_startup() -> None:
    env = {
        "ENVIRONMENT": "production",
        "ALLOW_DEV_LOGIN": "true",
        "JWT_SECRET": "x" * 64,
        "GEMINI_API_KEY": "test-api-key-1234567890",
        "DATABASE_URL": "postgresql+psycopg2://rag:strong_password_123@db:5432/rag",
        "REDIS_URL": "redis://redis:6379/0",
    }
    payload = _run_startup(env)
    assert payload["ok"] is False
    assert "ALLOW_DEV_LOGIN" in (payload["error"] or "")


def test_production_rejects_gemini_mock_mode() -> None:
    env = {
        "ENVIRONMENT": "production",
        "GEMINI_MOCK_MODE": "true",
        "ALLOW_DEV_LOGIN": "false",
        "JWT_SECRET": "x" * 64,
        "GEMINI_API_KEY": "test-api-key-1234567890",
        "DATABASE_URL": "postgresql+psycopg2://rag:strong_password_123@db:5432/rag",
        "REDIS_URL": "redis://redis:6379/0",
    }
    payload = _run_startup(env)
    assert payload["ok"] is False
    assert payload.get("error")


def test_production_rejects_weak_jwt_secret() -> None:
    env = {
        "ENVIRONMENT": "production",
        "ALLOW_DEV_LOGIN": "false",
        "JWT_SECRET": "short",
        "GEMINI_API_KEY": "test-api-key-1234567890",
        "DATABASE_URL": "postgresql+psycopg2://rag:strong_password_123@db:5432/rag",
        "REDIS_URL": "redis://redis:6379/0",
    }
    payload = _run_startup(env)
    assert payload["ok"] is False
    assert "JWT_SECRET" in (payload["error"] or "")


def test_production_requires_redis_when_flagged() -> None:
    env = {
        "ENVIRONMENT": "production",
        "ALLOW_DEV_LOGIN": "false",
        "JWT_SECRET": "x" * 64,
        "GEMINI_API_KEY": "test-api-key-1234567890",
        "DATABASE_URL": "postgresql+psycopg2://rag:strong_password_123@db:5432/rag",
        # Simulate missing Redis URL while REQUIRE_REDIS_IN_PRODUCTION=true
        "REDIS_URL": "",
    }
    payload = _run_startup(env)
    assert payload["ok"] is False
    assert "REDIS_URL" in (payload["error"] or "") or "Redis is required" in (payload["error"] or "")
