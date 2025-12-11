import datetime
import hashlib
import json
import logging
import sys
import traceback
from contextvars import ContextVar
from typing import Dict, Optional

# Per-request context injected by middleware/dependencies
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_user_id_ctx: ContextVar[Optional[int]] = ContextVar("user_id", default=None)


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter that preserves structured fields and request context."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {}
        if isinstance(record.msg, dict):
            payload.update(record.msg)
            payload.setdefault("message", record.msg.get("msg") or record.msg.get("event"))
        else:
            payload["message"] = record.getMessage()

        payload.setdefault("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
        payload.setdefault("level", record.levelname)
        payload.setdefault("logger", record.name)

        rid = getattr(record, "request_id", None) or _request_id_ctx.get()
        if rid:
            payload.setdefault("request_id", rid)
        uid = getattr(record, "user_id", None) or _user_id_ctx.get()
        if uid is not None:
            payload.setdefault("user_id", uid)

        # Avoid duplicating msg key alongside message
        payload.pop("msg", None)

        # Carry through selected extras into a context object for observability.
        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
        }
        context_fields = {
            k: v for k, v in record.__dict__.items() if k not in reserved and k not in payload and not k.startswith("_")
        }
        if context_fields:
            payload.setdefault("context", _scrub_header_fields(context_fields))

        payload = _scrub_header_fields(payload)

        if record.exc_info:
            payload["stack"] = "".join(traceback.format_exception(*record.exc_info))
        if record.stack_info:
            payload.setdefault("stack", record.stack_info)

        return json.dumps(payload, default=str)


def setup_logging():
    """Configure root logger to emit JSON structured logs."""
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    if not root.handlers:
        root.addHandler(handler)
    else:
        for h in root.handlers:
            h.setFormatter(JsonFormatter())
    root.setLevel(logging.INFO)
    return root


def bind_request_context(request_id: Optional[str]) -> object:
    """Bind the current request_id into a contextvar (returns reset token)."""
    return _request_id_ctx.set(request_id)


def clear_request_context(token: object | None = None) -> None:
    try:
        if token is not None:
            _request_id_ctx.reset(token)
        else:
            _request_id_ctx.set(None)
    except Exception:
        _request_id_ctx.set(None)


def bind_user_context(user_id: Optional[int]) -> object:
    """Bind the current user_id into a contextvar (returns reset token)."""
    return _user_id_ctx.set(user_id)


def clear_user_context(token: object | None = None) -> None:
    try:
        if token is not None:
            _user_id_ctx.reset(token)
        else:
            _user_id_ctx.set(None)
    except Exception:
        _user_id_ctx.set(None)


def email_hash(email: str) -> str:
    """
    Hash an email address for PII-safe logging.
    Returns first 16 characters of SHA256 hash.
    """
    return hashlib.sha256(email.encode()).hexdigest()[:16]


def scrub_sensitive_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Scrub sensitive headers from request headers for safe logging.
    Replaces values of sensitive headers with [REDACTED].
    """
    sensitive_headers = {
        "authorization",
        "cookie",
        "x-api-key",
        "x-internal-api-key",
        "proxy-authorization",
        "set-cookie",
    }

    def _is_secretish(header: str) -> bool:
        h = header.lower()
        if h in sensitive_headers:
            return True
        return any(h.endswith(suffix) for suffix in ("-token", "-secret", "-key"))

    return {k: ("[REDACTED]" if _is_secretish(k) else v) for k, v in headers.items()}


def _scrub_header_fields(payload: Dict[str, object]) -> Dict[str, object]:
    """
    Scrub any header-like fields on a logging payload to avoid leaking secrets.
    """
    header_keys = {"headers", "request_headers", "response_headers"}
    cleaned: Dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(key, str) and key.lower() in header_keys and isinstance(value, dict):
            cleaned[key] = scrub_sensitive_headers(value)
        else:
            cleaned[key] = value
    return cleaned


def log_json(level: int, msg: str, **fields):
    payload = {"event": msg, **fields}
    payload = _scrub_header_fields(payload)
    rid = _request_id_ctx.get()
    if rid:
        payload.setdefault("request_id", rid)
    uid = _user_id_ctx.get()
    if uid is not None:
        payload.setdefault("user_id", uid)
    logging.getLogger().log(level, payload)
