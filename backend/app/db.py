from typing import Any, Generator

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from .config import settings

is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine_kwargs = {
    "echo": False,
    "future": True,
    "connect_args": connect_args,
}
if not is_sqlite:
    engine_kwargs.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

engine = create_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def create_engine_from_settings(current_settings: Any = settings) -> Engine:
    """Factory for creating an engine from settings (injectable for tests)."""
    is_sqlite_local = current_settings.DATABASE_URL.startswith("sqlite")
    connect_args_local = {"check_same_thread": False} if is_sqlite_local else {}
    kwargs = {
        "echo": False,
        "future": True,
        "connect_args": connect_args_local,
    }
    if not is_sqlite_local:
        kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800)
    return create_engine(current_settings.DATABASE_URL, **kwargs)


def create_session_factory(bind_engine: Engine) -> sessionmaker:
    """Create a sessionmaker bound to the given engine."""
    return sessionmaker(bind=bind_engine, autoflush=False, autocommit=False, future=True)


def get_session_factory(request: Request) -> sessionmaker:
    """Return a SessionLocal factory, preferring app.state when available."""
    return getattr(request.app.state, "SessionLocal", SessionLocal)


def get_db(request: Request) -> Generator[Session, None, None]:
    """
    Yield a database session.

    Notes:
    - No implicit commit to avoid holding open transactions for streaming/SSE.
    """
    SessionFactory = get_session_factory(request)
    db: Session = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def ping_db(timeout_ms: int = 200) -> bool:
    try:
        with engine.connect() as conn:
            conn.execution_options(timeout=timeout_ms / 1000.0)
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
