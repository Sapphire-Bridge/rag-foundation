import time
import uuid
import re
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from .telemetry import (
    bind_request_context,
    clear_request_context,
    clear_user_context,
    log_json,
    scrub_sensitive_headers,
)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Get correlation ID from header, validate it, or generate new one
        cid = request.headers.get("X-Request-ID")

        # Validate client-provided correlation ID (alphanumeric + hyphens, 8-64 chars)
        if cid and re.fullmatch(r"[A-Za-z0-9\-]{8,64}", cid):
            rid = cid[:64]  # Truncate to 64 chars max
        else:
            # Invalid or missing - generate new UUID
            rid = str(uuid.uuid4())

        request.state.request_id = rid
        ctx_token = bind_request_context(rid)
        clear_user_context()  # reset any user binding before handling request
        start = time.perf_counter()
        headers = scrub_sensitive_headers(dict(request.headers))
        try:
            response: Response = await call_next(request)
        except Exception as e:
            dur_ms = int((time.perf_counter() - start) * 1000)
            log_json(
                40,
                "request_failed",
                request_id=rid,
                path=request.url.path,
                method=request.method,
                dur_ms=dur_ms,
                request_headers=headers,
                error=str(e),
            )
            raise
        finally:
            # Ensure contextvars are cleared even if response creation fails
            try:
                dur_ms = int((time.perf_counter() - start) * 1000)
                if "response" in locals():
                    response.headers["X-Request-ID"] = rid
                    log_json(
                        20,
                        "request_complete",
                        request_id=rid,
                        path=request.url.path,
                        method=request.method,
                        status=response.status_code,
                        dur_ms=dur_ms,
                        request_headers=headers,
                    )
            finally:
                clear_request_context(ctx_token)
                clear_user_context()
        return response
