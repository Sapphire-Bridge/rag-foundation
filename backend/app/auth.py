# SPDX-License-Identifier: Apache-2.0

import time
import uuid
import logging
from typing import Any, Optional, Protocol, cast

import bcrypt
from fastapi import Header, Depends, HTTPException, status
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User
from .telemetry import bind_user_context, log_json

ALGORITHM = "HS256"
BCRYPT_MAX_BYTES = 72


class PasswordValidationError(ValueError):
    """Raised when a password fails policy checks."""


_SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?/~`"

# Redis connection for JWT revocation (optional, only in production)


class _RevocationClient(Protocol):
    def setex(self, name: str, time: int, value: str) -> Any: ...

    def exists(self, name: str) -> int: ...


_rev: _RevocationClient | None = None
if settings.REDIS_URL:
    try:
        import redis

        _rev = cast(_RevocationClient, redis.Redis.from_url(settings.REDIS_URL, decode_responses=True))
    except Exception:
        _rev = None

_revocation_warning_logged = False
_revocation_fallback_logged = False


def _log_revocation_degraded(reason: str) -> None:
    """Emit a single structured warning when revocation is degraded/disabled."""
    global _revocation_warning_logged
    if _revocation_warning_logged:
        return
    _revocation_warning_logged = True
    try:
        log_json(30, "auth_revocation_degraded", reason=reason)
    except Exception:
        logging.warning("JWT revocation degraded: %s", reason)


def _log_revocation_fallback(reason: str) -> None:
    """Log once when revocation falls back during request handling."""
    global _revocation_fallback_logged
    if _revocation_fallback_logged:
        return
    _revocation_fallback_logged = True
    try:
        log_json(30, "auth_revocation_fallback", reason=reason)
    except Exception:
        logging.warning("JWT revocation fallback: %s", reason)


# Surface missing Redis at startup rather than per-request.
if settings.REDIS_URL and _rev is None:
    _log_revocation_degraded("redis not configured; skipping revocation checks")


def _now() -> int:
    return int(time.time())


def _bcrypt_safe(password: str) -> str:
    """
    Ensure passwords never exceed bcrypt's 72-byte limit.
    Truncates long UTF-8 strings deterministically and logs once.
    """
    if password is None:
        return ""
    encoded = password.encode("utf-8")
    if len(encoded) <= BCRYPT_MAX_BYTES:
        return password
    logging.warning("Incoming password exceeded 72 bytes; truncating for bcrypt compatibility.")
    return encoded[:BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")


def validate_password_policy(password: str) -> None:
    """
    Enforce registration/bootstrap password policy.

    - Minimum length: 6 characters
    - Maximum length: 72 bytes (bcrypt limit)
    - Must include upper, lower, digit, and special character
    """
    if password is None or password == "":
        raise PasswordValidationError("Password cannot be empty.")
    if len(password) < 6:
        raise PasswordValidationError("Password too short: minimum 6 characters.")
    # bcrypt silently truncates passwords >72 bytes; enforce limit to avoid confusing errors
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise PasswordValidationError("Password too long: must be 72 bytes or fewer.")
    if not (
        any(c.islower() for c in password) and any(c.isupper() for c in password) and any(c.isdigit() for c in password)
    ):
        raise PasswordValidationError("Weak password: require upper, lower, digit")
    if not any(c in _SPECIAL_CHARS for c in password):
        raise PasswordValidationError("Weak password: require a special character")


def hash_password(password: str) -> str:
    safe = _bcrypt_safe(password)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(safe.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_bcrypt_safe(plain).encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(*, user_id: int, email: str = "") -> str:
    """
    Create JWT access token containing only user_id in 'sub' claim.

    Security notes:
    - Email is NOT included in JWT to minimize PII exposure
    - Short token lifetime (ACCESS_TOKEN_EXPIRE_HOURS) limits exposure window
    - JTI (JWT ID) is included to allow server-side revocation via /logout
    """
    iat = _now()
    exp = iat + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": str(user_id),  # Only user ID, not email (keeps PII out of JWT)
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": iat,
        "exp": exp,
        "jti": str(uuid.uuid4()),  # JWT ID for revocation tracking
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def revoke_jti(jti: str, exp: int) -> None:
    """
    Revoke a JWT by storing its JTI in Redis until expiration.

    Args:
        jti: JWT ID to revoke
        exp: Token expiration timestamp (used to set Redis TTL)
    """
    if _rev is not None and jti:
        ttl = max(0, exp - int(time.time()))
        if ttl > 0:
            _rev.setex(f"revoked:{jti}", ttl, "1")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
        options={"verify_aud": True, "verify_signature": True, "verify_exp": True},
    )


def get_authorization(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return authorization.split(" ", 1)[1]


def get_current_user(db: Session = Depends(get_db), token: str = Depends(get_authorization)) -> User:
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        user_id = int(sub)
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Check if token has been revoked
    jti = payload.get("jti")
    if _rev is not None and isinstance(jti, str) and jti:
        try:
            if _rev.exists(f"revoked:{jti}"):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")
        except HTTPException:
            # Propagate explicit revocation decisions
            raise
        except Exception as exc:
            _log_revocation_fallback(f"redis error during revocation check: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Revocation service unavailable; please retry shortly",
            )

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
    try:
        bind_user_context(user.id)
    except Exception:
        pass
    return user


def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """
    Require admin access based on user flag.
    """
    if user.is_admin:
        return user

    log_json(30, "admin_access_denied", user_id=user.id)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
