"""
Test configuration with proper isolation guarantees.

Key invariants:
- No external HTTP calls (httpx/requests blocked)
- DB isolation via nested transactions (SAVEPOINT) + dependency override
- Deterministic time via freezegun
- Settings patched via monkeypatch
"""

import os
import pytest
from typing import Any, Generator

# ============================================================================
# Environment setup BEFORE any app imports
# ============================================================================

os.environ["ENVIRONMENT"] = "test"

# Provide a fake API key to satisfy config validation; outbound HTTP is blocked in tests.
os.environ["GEMINI_API_KEY"] = "test_api_key_blocked"
os.environ["GEMINI_MOCK_MODE"] = "true"

# Test conveniences
os.environ["REQUIRE_CSRF_HEADER"] = "false"
os.environ["ALLOW_DEV_LOGIN"] = "true"
os.environ["JWT_SECRET"] = "x" * 64

# ============================================================================
# Now safe to import app modules
# ============================================================================

from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from sqlalchemy import create_engine, event

from app.main import create_app
from app.db import get_db, get_session_factory
from app.models import Base
from app.config import settings


# ============================================================================
# Block external HTTP calls (NOT raw sockets - DB needs those)
# ============================================================================


@pytest.fixture(autouse=True)
def _block_http_clients(monkeypatch):
    """
    Block outbound HTTP calls via httpx and requests.

    We do NOT block raw sockets because:
    - PostgreSQL/MySQL connections require TCP sockets
    - SQLite uses file I/O, not sockets

    This catches the Gemini health probe and any other HTTP calls while leaving
    in-process ASGI transports alone.
    """

    def _blocked(*args, **kwargs):
        raise RuntimeError("HTTP call blocked in tests! Mock the external service.")

    # Block httpx convenience functions and network transports
    try:
        import httpx

        monkeypatch.setattr(httpx, "get", _blocked)
        monkeypatch.setattr(httpx, "post", _blocked)
        monkeypatch.setattr(httpx, "put", _blocked)
        monkeypatch.setattr(httpx, "delete", _blocked)
        monkeypatch.setattr(httpx, "request", _blocked)
        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked, raising=False)
        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked, raising=False)
    except ImportError:
        pass

    # Block requests (if used anywhere)
    try:
        import requests
        import requests.sessions

        monkeypatch.setattr(requests, "get", _blocked)
        monkeypatch.setattr(requests, "post", _blocked)
        monkeypatch.setattr(requests, "put", _blocked)
        monkeypatch.setattr(requests, "delete", _blocked)
        monkeypatch.setattr(requests, "request", _blocked)
        monkeypatch.setattr(requests.sessions.Session, "request", _blocked, raising=False)
    except ImportError:
        pass

    # Optionally block urllib for legacy code paths
    try:
        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    except ImportError:
        pass


# ============================================================================
# Database fixtures with proper SAVEPOINT isolation
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    """Placeholder to ensure ENV vars are set before app imports."""
    yield


@pytest.fixture
def db_connection(_setup_test_db):
    """Per-test SQLite database to guarantee isolation without global purges."""
    import tempfile
    import os

    db_fd, db_path = tempfile.mkstemp(prefix="test-db-", suffix=".sqlite")
    os.close(db_fd)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

    # Enforce foreign key constraints to match production RDBMS behavior.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine, SessionFactory, db_path
    finally:
        try:
            engine.dispose()
        finally:
            try:
                os.remove(db_path)
            except OSError:
                pass


@pytest.fixture
def session_factory(db_connection):
    """Session factory bound to the per-test engine."""
    _engine, SessionFactory, _db_path = db_connection
    return SessionFactory


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    """Per-test session; commits stay inside the test database."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app(session_factory, db_connection, monkeypatch):
    """
    FastAPI app with DB dependency overridden to use test session.
    """
    engine, _SessionFactory, _db_path = db_connection
    _app = create_app()
    # Ensure routes using app.state.SessionLocal pick up the test-bound factory with savepoint semantics
    _app.state.engine = engine
    _app.state.SessionLocal = session_factory
    try:
        import app.db as app_db

        monkeypatch.setattr(app_db, "engine", engine, raising=False)
        monkeypatch.setattr(app_db, "SessionLocal", session_factory, raising=False)
    except Exception:
        pass

    def _override_get_db(request: Request):
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    _app.dependency_overrides[get_db] = _override_get_db

    def _override_get_session_factory(request: Request):
        return session_factory

    _app.dependency_overrides[get_session_factory] = _override_get_session_factory

    yield _app

    _app.dependency_overrides.clear()


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """TestClient with proper lifecycle (triggers startup/shutdown)."""
    with TestClient(app) as c:
        yield c


# ============================================================================
# Auth helpers
# ============================================================================


@pytest.fixture
def auth_headers():
    """Factory for creating auth headers from a token."""

    def _make(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Requested-With": "XMLHttpRequest",
        }

    return _make


@pytest.fixture
def make_token():
    """
    Factory for creating JWT tokens for test users.

    Matches the actual create_access_token signature.
    """
    from app.auth import create_access_token

    def _make(user_id: int) -> str:
        return create_access_token(user_id=user_id)

    return _make


# ============================================================================
# Time control
# ============================================================================


@pytest.fixture
def frozen_time():
    """
    Freeze time across all modules.

    Uses freezegun for comprehensive coverage including:
    - time.time()
    - datetime.now()
    - 'from time import time' style imports

    Note: tick=False means time won't advance. Use frozen.tick() or
    frozen.move_to() to advance time for TTL tests.
    """
    from freezegun import freeze_time

    with freeze_time("2024-01-15 12:00:00", tick=False) as frozen:
        yield frozen


@pytest.fixture
def no_sleep(monkeypatch):
    """
    Block time.sleep to surface any unexpected sleeps.

    Raises RuntimeError instead of no-op so missed patches are caught.
    """
    import time as time_module

    def _blocked_sleep(seconds):
        raise RuntimeError(f"time.sleep({seconds}) called in test! Use frozen_time or mock the specific module.")

    monkeypatch.setattr(time_module, "sleep", _blocked_sleep)

    # Also patch known modules that import sleep directly
    _patch_module_sleep(monkeypatch, "app.services.ingestion")
    _patch_module_sleep(monkeypatch, "app.routes.chat")


def _patch_module_sleep(monkeypatch, module_path: str):
    """Patch sleep in a module if it exists."""
    if module_path not in {"app.services.ingestion", "app.routes.chat"}:
        return
    try:
        if module_path == "app.services.ingestion":
            import app.services.ingestion as ingestion_mod

            mod: Any = ingestion_mod
        elif module_path == "app.routes.chat":
            import app.routes.chat as chat_mod

            mod = chat_mod
        else:
            return
    except ImportError:
        return

    if hasattr(mod, "time"):
        monkeypatch.setattr(
            mod.time,
            "sleep",
            lambda _: (_ for _ in ()).throw(RuntimeError(f"sleep blocked in {module_path}")),
        )
    if hasattr(mod, "sleep"):
        monkeypatch.setattr(
            mod,
            "sleep",
            lambda _: (_ for _ in ()).throw(RuntimeError(f"sleep blocked in {module_path}")),
            raising=False,
        )


# ============================================================================
# Settings helpers
# ============================================================================


@pytest.fixture
def patch_settings(monkeypatch):
    """
    Factory for safely patching settings attributes.

    Usage:
        def test_something(patch_settings):
            patch_settings("RATE_LIMIT_PER_MINUTE", 5)
    """

    def _patch(attr: str, value):
        monkeypatch.setattr(settings, attr, value)

    return _patch


# ============================================================================
# Service fakes/mocks
# ============================================================================


@pytest.fixture
def fake_redis():
    """In-memory Redis fake."""
    from tests.fixtures.fakes import FakeRedis

    return FakeRedis()


@pytest.fixture
def mock_rag_client(monkeypatch):
    """
    Mock RAG client automatically injected into all relevant modules.

    Returns the fake so tests can configure responses.
    """
    from tests.fixtures.fakes import FakeRAGClient

    fake = FakeRAGClient()

    # Patch the canonical source
    monkeypatch.setattr("app.services.gemini_rag.get_rag_client", lambda: fake)

    # Patch other modules that may import it directly
    _safe_setattr(monkeypatch, "app.services.ingestion.get_rag_client", lambda: fake)
    _safe_setattr(monkeypatch, "app.routes.uploads.get_rag_client", lambda: fake)
    _safe_setattr(monkeypatch, "app.routes.chat.get_rag_client", lambda: fake)

    return fake


@pytest.fixture
def mock_gcs(monkeypatch):
    """Mock GCS client for storage tests."""
    from tests.fixtures.fakes import FakeGCSClient

    fake = FakeGCSClient()

    _safe_setattr(monkeypatch, "app.services.storage._require_storage_client", lambda: fake)

    return fake


def _safe_setattr(monkeypatch, target: str, value):
    """
    Patch a target, ignoring if it doesn't exist.

    This handles cases where module structure may vary.
    """
    try:
        monkeypatch.setattr(target, value)
    except (AttributeError, ImportError, ModuleNotFoundError):
        pass


# ============================================================================
# Logging helpers
# ============================================================================


@pytest.fixture
def capture_structured_logs(caplog):
    """
    Helper for asserting on structured JSON logs.

    Usage:
        def test_something(capture_structured_logs):
            # ... do something ...
            logs = capture_structured_logs()
            assert any(log.get("event") == "admin_access_denied" for log in logs)
    """
    import json

    def _parse_logs() -> list[dict]:
        parsed = []
        for record in caplog.records:
            try:
                if isinstance(record.msg, dict):
                    parsed.append(record.msg)
                elif isinstance(record.msg, str):
                    parsed.append(json.loads(record.msg))
            except (json.JSONDecodeError, TypeError):
                parsed.append(
                    {
                        "message": str(record.msg),
                        "level": record.levelname,
                        "logger": record.name,
                    }
                )
        return parsed

    return _parse_logs
