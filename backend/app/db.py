from sqlalchemy import create_engine, text
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


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
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
