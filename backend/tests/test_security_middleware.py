import time

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from ipaddress import ip_network
from starlette.datastructures import Headers
from starlette.requests import Request

from app.config import settings
from app.main import create_app
from app.rate_limit import limiter, _resolved_client_ip, _trusted_proxy_networks, rate_limit_middleware


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_csrf_header_required_when_enabled(client: TestClient) -> None:
    if not settings.REQUIRE_CSRF_HEADER:
        pytest.skip("CSRF header is disabled in this test configuration")

    # Missing CSRF header should fail for a state-changing endpoint
    r = client.post("/api/stores", json={"display_name": "CSRF Test"})
    assert r.status_code in (400, 403, 422)

    # With header it should succeed (or at least fail for other reasons)
    r2 = client.post(
        "/api/stores",
        json={"display_name": "CSRF Test"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r2.status_code != r.status_code


def test_rate_limit_hits_limit(client: TestClient) -> None:
    limiter.store.clear()

    limit = settings.RATE_LIMIT_PER_MINUTE
    url = "/health"

    with pytest.raises(HTTPException) as excinfo:
        for _ in range(limit + 5):
            client.get(url)
            time.sleep(0.01)

    assert excinfo.value.status_code == 429

    limiter.store.clear()


@pytest.fixture
def reset_trusted_proxies():
    original = list(_trusted_proxy_networks)
    yield
    _trusted_proxy_networks[:] = original
    assert _trusted_proxy_networks == original


def _fake_request(client_host: str, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": Headers(headers or {}).raw,
        "client": (client_host, 1234),
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_resolved_client_ip_prefers_forwarded_for_when_proxy_trusted(reset_trusted_proxies) -> None:
    _trusted_proxy_networks[:] = [ip_network("127.0.0.1/32")]
    req = _fake_request("127.0.0.1", {"x-forwarded-for": "203.0.113.9"})
    assert _resolved_client_ip(req) == "203.0.113.9"


def test_resolved_client_ip_ignores_forwarded_for_from_untrusted_proxy(reset_trusted_proxies) -> None:
    _trusted_proxy_networks[:] = [ip_network("10.0.0.0/8")]
    req = _fake_request("127.0.0.1", {"x-forwarded-for": "203.0.113.9"})
    assert _resolved_client_ip(req) == "127.0.0.1"


def test_resolved_client_ip_no_proxy_header_used(reset_trusted_proxies) -> None:
    _trusted_proxy_networks[:] = []
    req = _fake_request("203.0.113.9", {"X-Forwarded-For": "198.51.100.1"})
    assert _resolved_client_ip(req) == "203.0.113.9"


def test_resolved_client_ip_trusted_proxy_uses_first_xff(reset_trusted_proxies) -> None:
    _trusted_proxy_networks[:] = [ip_network("127.0.0.1/32")]
    req = _fake_request("127.0.0.1", {"X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
    assert _resolved_client_ip(req) == "203.0.113.9"


def test_resolved_client_ip_malformed_forwarded_for_falls_back(reset_trusted_proxies) -> None:
    _trusted_proxy_networks[:] = [ip_network("127.0.0.1/32")]
    req = _fake_request("127.0.0.1", {"X-Forwarded-For": "not-an-ip"})
    assert _resolved_client_ip(req) == "127.0.0.1"


def test_rate_limit_exceeded_for_same_ip(reset_trusted_proxies) -> None:
    """
    Executes the async middleware via asyncio.run to avoid needing pytest-asyncio.
    """
    import asyncio

    limiter.store.clear()
    _trusted_proxy_networks[:] = []

    async def call_next(_):
        return JSONResponse({"ok": True})

    limit = settings.RATE_LIMIT_PER_MINUTE
    req = _fake_request("203.0.113.9")

    async def _exercise():
        for _ in range(limit):
            resp = await rate_limit_middleware(req, call_next)
            assert resp.status_code == 200

        with pytest.raises(HTTPException) as excinfo:
            await rate_limit_middleware(req, call_next)
        assert excinfo.value.status_code == 429

    asyncio.run(_exercise())
    limiter.store.clear()
