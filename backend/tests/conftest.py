import os

import pytest


# Ensure required environment variables are present before app imports.
# Tests opt into dev login and disable CSRF explicitly; production defaults remain hardened.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "x" * 64)
os.environ.setdefault("GEMINI_API_KEY", "test_api_key_1234567890123456")
os.environ.setdefault("REQUIRE_CSRF_HEADER", "false")
os.environ.setdefault("ALLOW_DEV_LOGIN", "true")

# Apply test-friendly toggles before importing the app
try:
    from app.config import settings  # type: ignore

    settings.REQUIRE_CSRF_HEADER = False
except Exception:
    # In case the app isn't importable yet; the env var above still disables it
    pass


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    """Create database tables for tests using the app's SQLAlchemy metadata."""
    # Import after env is set so settings instantiate correctly
    from app.db import engine
    from app.models import Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Optional cleanup (keep DB state for debugging)
    # Base.metadata.drop_all(bind=engine)
