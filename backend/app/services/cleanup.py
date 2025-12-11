# SPDX-License-Identifier: Apache-2.0

"""Background cleanup helpers for remote Gemini resources."""

from __future__ import annotations

import logging
import datetime
from fastapi import BackgroundTasks

from ..db import SessionLocal
from ..models import Document, Store
from ..services.gemini_rag import get_rag_client
from ..telemetry import log_json


def enqueue_store_cleanup(background: BackgroundTasks, *, store_id: int, store_fs_name: str) -> None:
    """Schedule remote cleanup for a deleted store."""
    background.add_task(_delete_remote_store, store_id, store_fs_name)


def enqueue_document_cleanup(background: BackgroundTasks, *, document_id: int) -> None:
    """Schedule remote cleanup for a deleted document."""
    background.add_task(_delete_remote_document, document_id)


def _delete_remote_store(store_id: int, store_fs_name: str) -> None:
    """Best-effort remote delete for Gemini File Search stores."""
    rag = get_rag_client()
    try:
        rag.delete_store(store_fs_name)
        log_json(20, "remote_store_deleted", store_id=store_id, store_name=store_fs_name)
    except Exception as exc:
        logging.exception(
            "Remote store cleanup failed",
            exc_info=exc,
            extra={"store_id": store_id, "store_name": store_fs_name},
        )


def _delete_remote_document(document_id: int, session_factory=None) -> None:
    """Best-effort cleanup for Gemini files belonging to a deleted document."""
    session_factory = session_factory or SessionLocal
    db = session_factory()
    try:
        doc = db.get(Document, document_id)
        if not doc or not doc.store:
            return
        gemini_file_id = getattr(doc, "gemini_file_id", None)
        if not gemini_file_id:
            log_json(
                20,
                "remote_document_delete_skipped_no_file_id",
                document_id=document_id,
                store_id=getattr(doc, "store_id", None),
            )
            return
        rag = get_rag_client()
        try:
            rag.delete_document_from_store(doc.store.fs_name, doc.id, doc.filename, file_id=gemini_file_id)
            log_json(
                20,
                "remote_document_deleted",
                document_id=document_id,
                store_id=doc.store_id,
                file_id=gemini_file_id,
            )
        except NotImplementedError:
            log_json(
                20,
                "remote_document_delete_not_supported",
                document_id=document_id,
                store_id=doc.store_id,
                file_id=gemini_file_id,
            )
    except Exception as exc:
        logging.exception(
            "Remote document cleanup failed",
            exc_info=exc,
            extra={"document_id": document_id},
        )
    finally:
        db.close()


def cleanup_stale_stores(*, grace_hours: int = 48, batch_size: int = 50, session_factory=None) -> None:
    """
    Background janitor for soft-deleted or expired stores.
    Safe guardrails: grace period, batch limit, skip if active docs remain.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=grace_hours)
    session_factory = session_factory or SessionLocal
    db = session_factory()
    deleted = 0
    skipped = 0
    try:
        candidates = (
            db.query(Store)
            .filter(Store.deleted_at.isnot(None), Store.deleted_at < cutoff)
            .order_by(Store.deleted_at.asc())
            .limit(batch_size)
            .all()
        )
        for store in candidates:
            active_docs = (
                db.query(Document).filter(Document.store_id == store.id, Document.deleted_at.is_(None)).count()
            )
            if active_docs:
                skipped += 1
                continue

            rag = get_rag_client()
            try:
                rag.delete_store(store.fs_name)
                db.delete(store)
                db.commit()
                deleted += 1
            except Exception as exc:  # pragma: no cover - best effort
                db.rollback()
                logging.exception(
                    "Cleanup failed for store %s", store.id, exc_info=exc, extra={"store_name": store.fs_name}
                )
        logging.info("Store cleanup run", extra={"deleted": deleted, "skipped": skipped})
    finally:
        db.close()
