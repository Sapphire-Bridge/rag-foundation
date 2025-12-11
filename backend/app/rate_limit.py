# SPDX-License-Identifier: Apache-2.0

import ipaddress
import logging
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from .config import settings
from .telemetry import log_json

try:
    import redis
except Exception:
    redis = None


class InMemoryRateLimiter:
    """Lightweight dev/test fallback; not intended for high-concurrency or multi-process use."""

    def __init__(self, max_keys: int = 5000, key_ttl_seconds: int = 900):
        # max_keys bounds the number of tracked principals; key_ttl_seconds prunes idle keys.
        self.store: dict[str, Deque[float]] = defaultdict(deque)
        self.last_seen: dict[str, float] = {}
        self.max_keys = max_keys
        self.key_ttl_seconds = key_ttl_seconds

    def _prune(self, now: float, window: int) -> None:
        cutoff = now - max(window, self.key_ttl_seconds)
        stale = [k for k, ts in self.last_seen.items() if ts < cutoff]
        for key in stale:
            self.store.pop(key, None)
            self.last_seen.pop(key, None)

    def _evict_if_needed(self) -> None:
        if len(self.last_seen) < self.max_keys:
            return
        oldest_key = min(self.last_seen, key=self.last_seen.get)
        self.store.pop(oldest_key, None)
        self.last_seen.pop(oldest_key, None)

    def check(self, key: str, limit: int, window: int) -> tuple[int, int]:
        """Returns (remaining, limit) for rate limit headers."""
        # Note: no locks; acceptable for single-process dev/test fallback.
        now = time.time()
        self._prune(now, window)
        q = self.store.get(key)
        if q is None:
            self._evict_if_needed()
            q = self.store[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        q.append(now)
        self.last_seen[key] = now
        return (limit - len(q), limit)


class RedisRateLimiter:
    def __init__(self, client: "redis.Redis"):
        self.client = client

    def check(self, key: str, limit: int, window: int) -> tuple[int, int]:
        now = int(time.time())
        bucket = now // window
        rk = f"ratelimit:{key}:{bucket}"

        with self.client.pipeline() as pipe:
            pipe.incr(rk)
            pipe.expire(rk, window * 2)
            count, _ = pipe.execute()

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        remaining = max(0, limit - count)
        return remaining, limit


class RateLimiter:
    def __init__(self, redis_client: "redis.Redis | None"):
        self._memory_limiter = InMemoryRateLimiter()
        self._redis_limiter = RedisRateLimiter(redis_client) if redis_client else None
        self._fallback_logged = False
        self._no_redis_logged = False

    @property
    def store(self):
        # Expose in-memory store for tests/backwards compatibility.
        return self._memory_limiter.store

    def check(self, key: str, limit: int, window: int) -> tuple[int, int]:
        if self._redis_limiter is None:
            if settings.REDIS_URL and not self._no_redis_logged:
                self._no_redis_logged = True
                try:
                    log_json(30, "ratelimit_degraded", reason="redis not configured; using in-memory limiter")
                except Exception:
                    logging.warning("Redis not configured for rate limiting; using in-memory limiter.")
            return self._memory_limiter.check(key, limit, window)

        try:
            return self._redis_limiter.check(key, limit, window)
        except HTTPException:
            raise
        except Exception as exc:  # Fallback if Redis is down/misconfigured
            if not self._fallback_logged:
                self._fallback_logged = True
                try:
                    log_json(30, "ratelimit_degraded", reason=f"redis error: {exc}")
                except Exception:
                    logging.warning("Redis rate limiting error, using in-memory fallback: %s", exc)
            return self._memory_limiter.check(key, limit, window)


_r = None
if settings.REDIS_URL and redis is not None:
    try:
        _r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as exc:
        logging.warning("Failed to init Redis for rate limiting: %s", exc)
        _r = None

limiter = RateLimiter(_r)

_trusted_proxy_networks = [ipaddress.ip_network(cidr, strict=False) for cidr in settings.TRUSTED_PROXY_IPS]


def _resolved_client_ip(request: Request) -> str:
    """Resolve client IP, honoring X-Forwarded-For when behind a trusted proxy."""
    client_host = request.client.host if request.client else None
    if not client_host:
        return "unknown"

    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return client_host

    if _trusted_proxy_networks and any(client_ip in net for net in _trusted_proxy_networks):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            forwarded_for = xff.split(",")[0].strip()
            try:
                return str(ipaddress.ip_address(forwarded_for))
            except ValueError:
                # Malformed header; fall back to the proxy client IP
                return str(client_ip)

    return str(client_ip)


def check_rate_limit(key: str, limit: int, window: int = 60) -> tuple[int, int]:
    """
    Enforce a fixed-window rate limit for the given key.

    Returns (remaining, limit) for header decoration.
    """
    return limiter.check(key, limit, window)


async def rate_limit_middleware(request: Request, call_next):
    ip = _resolved_client_ip(request)
    key = f"ip:{ip}"
    authz = request.headers.get("authorization")
    if authz and authz.lower().startswith("bearer "):
        token = authz.split(" ", 1)[1]
        try:
            from .auth import decode_token

            payload = decode_token(token)
            sub = payload.get("sub")
            if sub:
                key = f"user:{sub}"
        except Exception:
            pass

    remaining = 0
    limit = settings.RATE_LIMIT_PER_MINUTE

    try:
        remaining, _ = check_rate_limit(key, limit)
    except HTTPException as exc:
        # Return a proper response so outer middleware (correlation, etc.) can decorate it.
        headers = exc.headers or {}
        headers.setdefault("X-RateLimit-Limit", str(limit))
        headers.setdefault("X-RateLimit-Remaining", "0")
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)

    response = await call_next(request)
    # Add rate limit headers to response (best-effort)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response
