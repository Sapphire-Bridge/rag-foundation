# SPDX-License-Identifier: Apache-2.0

"""ARQ worker/queue wiring for ingestion jobs."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Optional
from urllib.parse import unquote, urlparse

from arq import cron, run_worker
from arq.connections import RedisSettings, create_pool

from sqlalchemy import func

from app.config import settings
from app.db import SessionLocal
from app.models import Document, DocumentStatus, Store
from app.services.ingestion import index_document_job
from app.telemetry import setup_logging

logger = logging.getLogger(__name__)
setup_logging()


def _redis_settings_from_url(url: Optional[str]) -> Optional[RedisSettings]:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"}:
        return None
    db_idx = 0
    if parsed.path and parsed.path != "/":
        try:
            db_idx = int(parsed.path.lstrip("/"))
        except ValueError:
            db_idx = 0
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=db_idx,
        password=unquote(parsed.password) if parsed.password else None,
        ssl=parsed.scheme == "rediss",
    )


_redis_settings = _redis_settings_from_url(settings.REDIS_URL)
_arq_pool = None
_pool_lock: Optional[asyncio.Lock] = None


async def get_worker_pool():
    global _arq_pool
    global _pool_lock
    if _arq_pool:
        return _arq_pool
    if _redis_settings is None:
        raise RuntimeError("Redis must be configured via REDIS_URL to enqueue ingestion jobs.")
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    async with _pool_lock:
        if _arq_pool:
            return _arq_pool
        _arq_pool = await create_pool(_redis_settings)
    return _arq_pool


async def enqueue_ingestion_job(store_id: int, document_id: int, local_path: str):
    pool = await get_worker_pool()
    return await pool.enqueue_job("index_document_job", store_id, document_id, local_path)


def has_ingestion_queue() -> bool:
    return _redis_settings is not None


async def reset_stuck_documents(_ctx, session_factory=None):
    """
    Cron task to reset documents stuck in RUNNING longer than WATCHDOG_TTL_MINUTES.
    """
    session_factory = session_factory or SessionLocal
    session = session_factory()
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=settings.WATCHDOG_TTL_MINUTES)
    try:
        docs = (
            session.query(Document)
            .join(Store)
            .filter(
                Document.status == DocumentStatus.RUNNING,
                func.coalesce(Document.status_updated_at, Document.created_at) < cutoff,
                Store.deleted_at.is_(None),
                Document.deleted_at.is_(None),
            )
            .all()
        )
        count = 0
        for doc in docs:
            doc.set_status(DocumentStatus.ERROR)
            doc.op_name = None
            count += 1
        session.commit()
        if count:
            logger.info("Watchdog reset stuck documents", extra={"count": count})
    except Exception as exc:  # pragma: no cover - telemetry only
        session.rollback()
        logger.error("Watchdog reset failed", exc_info=exc)
    finally:
        session.close()


class WorkerSettings:
    functions = [index_document_job, reset_stuck_documents]
    redis_settings = _redis_settings
    max_jobs = 10
    job_timeout = 300
    cron_jobs = [
        cron(
            reset_stuck_documents,
            minute={m for m in range(0, 60, max(1, settings.WATCHDOG_CRON_MINUTES))},
        )
    ]


def run_worker_main() -> None:
    if _redis_settings is None:
        raise RuntimeError("Redis must be available to start the ingestion worker.")
    run_worker("app.worker.WorkerSettings")


if __name__ == "__main__":
    run_worker_main()
