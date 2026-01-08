# SPDX-License-Identifier: Apache-2.0

"""
Security gate module: Validates critical security settings at startup.
Fails fast if the application is misconfigured in production.
"""

import logging
from .config import settings, DEV_DEFAULT_JWT_SECRET

logger = logging.getLogger(__name__)


def run_security_gate() -> None:
    """
    Run security checks at startup. Raises RuntimeError if critical security
    requirements are not met.

    This function enforces:
    - ALLOW_DEV_LOGIN must be false in production
    - JWT_SECRET must be strong (validated in config)
    - REDIS_URL must be set in production (validated in config)
    - GEMINI_API_KEY must be set (validated in config)
    """
    logger.info("Running security gate checks...")
    env = settings.ENVIRONMENT.lower()
    prod_like = env in {"staging", "production"}

    if prod_like and not settings.STRICT_MODE:
        raise RuntimeError("STRICT_MODE cannot be disabled in staging/production environments.")

    # Dev login must never be enabled outside dev/test
    if settings.ALLOW_DEV_LOGIN and prod_like:
        raise RuntimeError(
            "CRITICAL SECURITY ERROR: ALLOW_DEV_LOGIN must be false outside development/test. "
            "This setting bypasses authentication and MUST NOT be enabled in staging or production environments."
        )

    # Additional security checks (these are also validated in Settings validators)
    # We check them here for explicit, fail-fast behavior with clear error messages

    if not settings.JWT_SECRET:
        raise RuntimeError("CRITICAL SECURITY ERROR: JWT_SECRET is not set")
    secret = settings.JWT_SECRET or ""
    if prod_like and (len(secret) < 32 or secret == DEV_DEFAULT_JWT_SECRET or "dev_secret" in secret):
        raise RuntimeError("CRITICAL SECURITY ERROR: Weak JWT_SECRET detected; set a unique 32+ character secret.")

    if settings.GEMINI_MOCK_MODE:
        if prod_like and not settings.ALLOW_MOCK_IN_PROD:
            raise RuntimeError(
                "GEMINI_MOCK_MODE is enabled but only allowed in development/test environments "
                "unless ALLOW_MOCK_IN_PROD=true is explicitly set."
            )
        if prod_like and settings.ALLOW_MOCK_IN_PROD:
            logger.warning("GEMINI_MOCK_MODE enabled in %s with ALLOW_MOCK_IN_PROD=true.", env)
        else:
            logger.info("Gemini mock mode enabled - real API calls are disabled.")
    else:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("CRITICAL SECURITY ERROR: GEMINI_API_KEY is not set")

    # CSRF must not be disabled in staging/production; warn only in dev/test
    if not settings.REQUIRE_CSRF_HEADER:
        if prod_like:
            raise RuntimeError(
                "CRITICAL SECURITY ERROR: CSRF protection is disabled (REQUIRE_CSRF_HEADER=false). "
                "Enable it for all staging/production environments."
            )
        logger.warning(
            "CSRF protection is disabled (REQUIRE_CSRF_HEADER=false). "
            "This should only be used in development environments."
        )

    # Warn about metadata filter being enabled (currently disabled by default)
    if settings.ALLOW_METADATA_FILTERS:
        logger.warning(
            "Metadata filters are enabled (ALLOW_METADATA_FILTERS=true). "
            "Ensure proper validation is in place to prevent injection attacks."
        )

    if prod_like and settings.REQUIRE_REDIS_IN_PRODUCTION:
        if not settings.REDIS_URL:
            raise RuntimeError(
                "CRITICAL SECURITY ERROR: REDIS_URL must be set in staging/production when Redis is required."
            )
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - startup guard
            raise RuntimeError(
                "CRITICAL SECURITY ERROR: Redis driver not installed. "
                "Install the 'redis' package or disable REQUIRE_REDIS_IN_PRODUCTION (not recommended for prod)."
            ) from exc
        try:
            client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
            if not client.ping():
                raise RuntimeError("Redis ping failed")
        except Exception as exc:  # pragma: no cover - startup guard
            raise RuntimeError("CRITICAL SECURITY ERROR: Redis is required but unreachable.") from exc

    logger.info("Security gate checks passed")
