# SPDX-License-Identifier: Apache-2.0

import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from .config import settings
from .telemetry import (
    bind_request_context,
    clear_request_context,
    clear_user_context,
    log_json,
    scrub_sensitive_headers,
    setup_logging,
)
from .rate_limit import rate_limit_middleware
from .metrics import metrics_endpoint
from .db import ping_db
from .routes import auth as auth_routes
from .routes import stores, uploads, chat, costs, documents, admin
from .routes import settings as settings_routes
from .services.gemini_rag import get_rag_client
from .security_gate import run_security_gate


class HealthStatus(BaseModel):
    database: bool
    gemini_api: bool
    redis: bool


logger = setup_logging()


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Assistant Backend", version="0.2.1")

    @app.on_event("startup")
    async def validate_config_on_startup():
        """Validate critical config on startup - fail fast if misconfigured."""
        logger.info("Validating configuration at startup...")
        try:
            # Config validation happens during Settings instantiation via validators
            # This explicit check ensures we fail fast if config is invalid
            assert settings.JWT_SECRET, "JWT_SECRET validation failed"
            if not settings.GEMINI_MOCK_MODE:
                assert settings.GEMINI_API_KEY, "GEMINI_API_KEY validation failed"
            else:
                logger.warning("GEMINI_MOCK_MODE enabled - skipping real Gemini API key validation.")
            logger.info("Configuration validation passed")

            # Run security gate checks
            run_security_gate()

        except (ValueError, AssertionError) as e:
            logger.error(f"Configuration validation failed: {e}")
            raise RuntimeError(f"Invalid configuration: {e}") from e

    @app.middleware("http")
    async def _correlation_id(request: Request, call_next):
        """Assign or propagate a request ID and ensure it reaches logs and responses."""
        cid = request.headers.get("X-Request-ID")
        if not cid or not re.fullmatch("[A-Za-z0-9-]{8,64}", cid):
            cid = str(uuid.uuid4())

        request.state.request_id = cid
        ctx_token = bind_request_context(cid)
        clear_user_context()
        start = time.perf_counter()
        headers = scrub_sensitive_headers(dict(request.headers))
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            dur_ms = int((time.perf_counter() - start) * 1000)
            log_json(
                40,
                "request_failed",
                path=request.url.path,
                method=request.method,
                dur_ms=dur_ms,
                error=str(exc),
                request_headers=headers,
            )
            raise
        finally:
            try:
                if "response" in locals():
                    response.headers["X-Request-ID"] = cid
                    dur_ms = int((time.perf_counter() - start) * 1000)
                    log_json(
                        20,
                        "request_complete",
                        path=request.url.path,
                        method=request.method,
                        status=response.status_code,
                        dur_ms=dur_ms,
                        request_headers=headers,
                    )
            finally:
                clear_request_context(ctx_token)
                clear_user_context()

    app.middleware("http")(rate_limit_middleware)

    # CSRF protection via custom header requirement
    @app.middleware("http")
    async def _csrf_protection(request: Request, call_next):
        """Require X-Requested-With header for state-changing operations."""
        if settings.REQUIRE_CSRF_HEADER and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            # Skip CSRF check for health/metrics endpoints
            if request.url.path not in {"/health", "/metrics"}:
                if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                    return JSONResponse(
                        status_code=403, content={"detail": "CSRF check failed: X-Requested-With header required"}
                    )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.CORS_ORIGINS] or ["http://localhost:5173"],
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
        expose_headers=["x-vercel-ai-ui-message-stream", "X-Request-ID"],
    )

    @app.middleware("http")
    async def _http_metrics_middleware(request, call_next):
        """Record HTTP request metrics: count and duration per method+endpoint+status."""
        from .metrics import http_requests_total, http_request_duration
        import time

        start = time.perf_counter()
        method = request.method
        # Extract endpoint pattern (e.g., /api/chat instead of /api/chat?foo=bar)
        endpoint = request.url.path
        route = request.scope.get("route")
        if route:
            endpoint = getattr(route, "path", None) or getattr(route, "name", None) or endpoint

        response = await call_next(request)
        duration = time.perf_counter() - start
        status = str(response.status_code)

        # Record metrics
        http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
        http_request_duration.labels(method=method, endpoint=endpoint).observe(duration)

        return response

    def _csp_directives() -> list[str]:
        allow_inline = settings.ENVIRONMENT in {"development", "test"}
        script_directive = "script-src 'self'" + (" 'unsafe-inline'" if allow_inline else "")
        style_directive = "style-src 'self'" + (" 'unsafe-inline'" if allow_inline else "")
        connect_targets = ["'self'", "https://generativelanguage.googleapis.com"]
        dev_origins = [str(o) for o in settings.CORS_ORIGINS] or ["http://localhost:5173"]
        if allow_inline:
            connect_targets.extend(dev_origins)
        connect_directive = "connect-src " + " ".join(dict.fromkeys(connect_targets))

        return [
            "default-src 'self'",
            script_directive,
            style_directive,
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            connect_directive,
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        """Add comprehensive security headers to all responses."""
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Download-Options", "noopen")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        # Content Security Policy
        response.headers.setdefault("Content-Security-Policy", "; ".join(_csp_directives()))

        # HSTS (only for HTTPS)
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")

        # Permissions Policy (restrict browser features)
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(),microphone=(),camera=(),payment=(),usb=(),magnetometer=(),gyroscope=(),accelerometer=()",
        )

        return response

    @app.middleware("http")
    async def _json_body_limit(request, call_next):
        from fastapi.responses import JSONResponse

        max_bytes = settings.MAX_JSON_MB * 1024 * 1024

        # Global guard: reject obviously oversized requests by Content-Length, except uploads which
        # have their own streaming limit and larger cap.
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > max_bytes and request.url.path != "/api/upload":
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})

        ct = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        is_json = ct == "application/json" or ct.endswith("+json")
        if not is_json:
            # For non-JSON requests without a Content-Length (e.g., chunked), enforce a soft cap by
            # consuming the stream up to max_bytes to avoid unbounded memory usage. Skip uploads,
            # which enforce their own streaming limits.
            te = (request.headers.get("transfer-encoding") or "").lower()
            if request.url.path != "/api/upload" and (not cl or "chunked" in te):
                received = 0
                chunks: list[bytes] = []
                try:
                    async for chunk in request.stream():
                        if not chunk:
                            continue
                        received += len(chunk)
                        if received > max_bytes:
                            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
                        chunks.append(chunk)
                except (RuntimeError, ValueError, TypeError):
                    return JSONResponse(status_code=400, content={"detail": "Invalid request body"})

                body = b"".join(chunks)
                request._body = body  # type: ignore[attr-defined]
                if hasattr(request, "_stream_consumed"):
                    request._stream_consumed = True  # type: ignore[attr-defined]
            return await call_next(request)

        received = 0
        chunks: list[bytes] = []
        try:
            async for chunk in request.stream():
                if not chunk:
                    continue
                received += len(chunk)
                if received > max_bytes:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large"})
                chunks.append(chunk)
        except (RuntimeError, ValueError, TypeError):
            return JSONResponse(status_code=400, content={"detail": "Invalid request body"})

        body = b"".join(chunks)

        request._body = body  # type: ignore[attr-defined]
        if hasattr(request, "_stream_consumed"):
            request._stream_consumed = True  # type: ignore[attr-defined]
        return await call_next(request)

    @app.exception_handler(Exception)
    async def _global_exc_handler(request, exc):
        from fastapi.responses import JSONResponse

        # Log exception for debugging while returning generic error to client
        logger.exception(
            f"Unhandled exception on {request.method} {request.url.path}",
            exc_info=exc,
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else "unknown",
            },
        )
        resp = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        rid = getattr(getattr(request, "state", None), "request_id", None)
        if rid:
            resp.headers["X-Request-ID"] = rid
        return resp

    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(stores.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(uploads.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(costs.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    @app.get(
        "/metrics",
        response_class=PlainTextResponse,
        responses={
            200: {"content": {"text/plain": {}}},
            403: {"description": "Forbidden"},
        },
    )
    async def metrics(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        if not settings.METRICS_ALLOW_ALL:
            # Restrict metrics endpoint to localhost by default; adjust for your infra as needed.
            if client_ip not in {"127.0.0.1", "::1"}:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
        return await metrics_endpoint()

    @app.get(
        "/health",
        response_model=HealthStatus,
        responses={
            200: {"model": HealthStatus},
            503: {"model": HealthStatus},
        },
    )
    def health():
        import logging
        from fastapi.responses import JSONResponse
        from .genai import errors
        import importlib

        db_ok = ping_db()
        redis_ok = True
        if settings.REDIS_URL:
            try:
                redis_mod = importlib.import_module("redis")
                client = redis_mod.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
                redis_ok = bool(client.ping())
            except Exception as exc:
                logging.warning("Redis health check failed: %s", exc)
                redis_ok = False
        # Gemini quick probe (models.list can be heavy; we do a lightweight no-op by instantiating client)
        try:
            rag = get_rag_client()
            gemini_ok = True
            if getattr(rag, "is_mock", False):
                logging.debug("Gemini mock mode active - skipping external health probe.")
        except (ImportError, TypeError, ValueError, errors.APIError) as e:
            logging.warning(f"Gemini health check failed: {e}")
            gemini_ok = False
        status = {"database": db_ok, "gemini_api": gemini_ok, "redis": redis_ok}
        code = 200 if db_ok and gemini_ok and redis_ok else 503
        return JSONResponse(status_code=code, content=status)

    return app


app = create_app()
