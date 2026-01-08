# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from typing import Any, Callable, Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from sqlalchemy.orm import Session

from app.config import settings
from app.costs import calc_index_cost, estimate_tokens_from_bytes
from app.db import SessionLocal
from app.metrics import token_usage_total
from app.models import Document, DocumentStatus, QueryLog, Store
from app.services.gemini_rag import (
    RETRYABLE_EXCEPTIONS,
    UploadResult,
    _extract_uploaded_file_id,
    get_rag_client,
)
from app.genai import redact_llm_error
from app.telemetry import log_json

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


@retry(
    stop=stop_after_attempt(settings.GEMINI_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=0.5, min=1, max=6),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True,
)
def _op_status(rag: Any, op_name: str) -> dict[str, Any]:
    return rag.op_status(op_name)


@retry(
    stop=stop_after_attempt(settings.GEMINI_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=0.5, min=1, max=6),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True,
)
def _upload_file_with_retry(rag: Any, store: Store, local_path: str, display_name: str | None) -> UploadResult:
    return rag.upload_file(store.fs_name, local_path, display_name=display_name)


def _cleanup_temp_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        return
    except OSError as exc:  # pragma: no cover - best effort cleanup
        logger.warning("Failed to remove temp file %s: %s", path, exc)


def _sanitize_error(exc: Exception | str) -> str:
    """
    Produce a sanitized, bounded error string safe for user-visible surfaces.
    """
    msg = str(exc) if exc is not None else "Unknown error"
    msg = re.sub(r"/[A-Za-z0-9._-]+/(tmp|var|app)[^\\s]*", "[path]", msg)
    return msg[:500]


def _log_index_cost(store: Store, document: Document, session_factory: SessionFactory | None = None) -> None:
    session_factory = session_factory or SessionLocal
    idx_tokens = estimate_tokens_from_bytes(document.size_bytes)
    idx_cost = calc_index_cost(idx_tokens)
    if idx_cost.total_cost_usd <= 0:
        return

    token_usage_total.labels(model="INDEX", type="index").inc(idx_tokens)

    db = session_factory()
    try:
        db.add(
            QueryLog(
                user_id=store.user_id,
                store_id=store.id,
                prompt_tokens=idx_tokens,
                completion_tokens=None,
                cost_usd=idx_cost.total_cost_usd,
                model="INDEX",
            )
        )
        db.commit()
    except Exception as exc:  # pragma: no cover - telemetry only
        logger.warning(
            "Failed to log index cost",
            exc_info=exc,
            extra={"document_id": getattr(document, "id", None), "store_id": getattr(store, "id", None)},
        )
        db.rollback()
    finally:
        db.close()


def _wait_for_operation_completion(rag: Any, op_name: str) -> None:
    """
    Poll the Gemini LRO until DONE or ERROR, with jitter and a hard timeout.
    """
    start = time.monotonic()
    wait = 2.0
    wait_max = 20.0
    while True:
        elapsed = time.monotonic() - start
        if elapsed > settings.GEMINI_INGESTION_TIMEOUT_S:
            raise TimeoutError(f"Ingestion timed out after {elapsed:.1f}s")

        try:
            stat = rag.op_status(op_name)
        except Exception as exc:
            log_json(
                30,
                "ingest_op_status_retry",
                op_name=op_name,
                retry_wait_ms=int(wait * 1000),
                **redact_llm_error(exc),
            )
            time.sleep(wait + random.uniform(0, 1.5))
            wait = min(wait * 1.5, wait_max)
            continue

        if stat.get("error"):
            raise RuntimeError(stat.get("error") or "Gemini ingestion failed")
        if stat.get("done"):
            return

        # Backoff with a little jitter to avoid thundering herd on operations.get
        time.sleep(wait + random.uniform(0, 1.5))
        wait = min(wait * 1.5, wait_max)


def run_ingestion_sync(
    store_id: int, document_id: int, local_path: str, session_factory: SessionFactory | None = None
) -> None:
    """
    Durable ingestion job executed by the worker (synchronous core).

    Steps:
    - validate doc/store ownership and soft-delete state
    - update status PENDING/ERROR -> RUNNING
    - upload to Gemini (with retries baked into client)
    - poll once for operation status; set DONE/ERROR accordingly
    - log index cost and clean up temp file
    """
    session_factory = session_factory or SessionLocal
    db = session_factory()
    store: Optional[Store] = None
    document: Optional[Document] = None
    op_name: Optional[str] = None
    uploaded_file_id: Optional[str] = None
    rag = None
    try:
        document = (
            db.query(Document)
            .filter(Document.id == document_id)
            .with_for_update(nowait=False, of=Document)
            .one_or_none()
        )
        if not document or document.deleted_at is not None:
            log_json(20, "ingest_skip_deleted_doc", document_id=document_id)
            return

        store = db.get(Store, store_id)
        if not store or store.deleted_at is not None or store.id != document.store_id:
            log_json(30, "ingest_store_not_found", store_id=store_id, document_id=document_id)
            document.last_error = "Store missing or deleted"
            document.set_status(DocumentStatus.ERROR)
            db.commit()
            return

        if document.status == DocumentStatus.DONE and not document.op_name:
            log_json(20, "ingest_already_done", document_id=document.id, store_id=store.id)
            return

        if document.op_name and document.status in (DocumentStatus.RUNNING, DocumentStatus.DONE):
            # Another ingestion is already in-flight or complete; avoid double-uploading.
            document.touch_status()  # Keep heartbeat fresh without altering status
            db.commit()
            log_json(
                20,
                "ingest_skip_existing_operation",
                document_id=document.id,
                store_id=store.id,
                status=document.status.value,
            )
            return

        # Only one worker should transition a document into RUNNING to avoid duplicate uploads.
        # If another worker already set RUNNING, skip this attempt.
        if document.status == DocumentStatus.RUNNING:
            log_json(
                20,
                "ingest_skip_already_running",
                document_id=document.id,
                store_id=store.id,
            )
            db.commit()
            return

        document.last_error = None
        document.set_status(DocumentStatus.RUNNING)
        db.commit()

        rag = get_rag_client()
        log_json(
            20,
            "ingest_upload_start",
            document_id=document.id,
            store_id=store.id,
            filename=document.filename,
        )

        upload_result: UploadResult | None = None
        if not document.op_name:
            upload_result = _upload_file_with_retry(rag, store, local_path, document.display_name or document.filename)
            op_name = upload_result.operation_name
            if op_name and len(op_name) > 255:
                logger.warning("Op name too long; truncating", extra={"document_id": document.id})
                op_name = op_name[:255]
            document.op_name = op_name
            if upload_result.file_id and not document.gemini_file_id:
                file_id = upload_result.file_id
                if len(file_id) > 255:
                    logger.warning("Gemini file id too long; truncating", extra={"document_id": document.id})
                    file_id = file_id[:255]
                document.gemini_file_id = file_id
                uploaded_file_id = file_id
            elif not upload_result.file_id:
                # Attempt to recover the file id from the operation status; if still missing, continue but warn.
                recovered_file_id: str | None = None
                try:
                    snapshot = rag.op_status(op_name)
                    recovered_file_id = _extract_uploaded_file_id(snapshot)
                    if not recovered_file_id and isinstance(snapshot, dict):
                        recovered_file_id = _extract_uploaded_file_id(snapshot.get("metadata"))
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Failed to recover Gemini file id after upload",
                        extra={
                            "document_id": document.id,
                            "store_id": store.id,
                            "error": str(exc),
                        },
                    )

                if recovered_file_id:
                    file_id = recovered_file_id[:255]
                    document.gemini_file_id = file_id
                    uploaded_file_id = file_id
                else:
                    logger.warning(
                        "Gemini upload response missing file id; continuing without remote delete handle",
                        extra={"document_id": document.id, "store_id": store.id},
                    )
        else:
            op_name = document.op_name
        if not op_name:
            raise RuntimeError("Gemini ingestion did not return an operation name")
        db.commit()

        try:
            _wait_for_operation_completion(rag, op_name)
        except TimeoutError as exc:
            log_json(
                20,
                "ingest_op_still_running",
                document_id=document.id,
                store_id=store.id,
                op_status="RUNNING",
                **redact_llm_error(exc),
            )
            document.last_error = _sanitize_error(exc)
            document.set_status(DocumentStatus.ERROR)
        except Exception as exc:
            log_json(
                30,
                "ingest_op_failed",
                document_id=document.id,
                store_id=store.id,
                op_name=op_name,
                **redact_llm_error(exc),
            )
            document.last_error = _sanitize_error(exc)
            document.set_status(DocumentStatus.ERROR)
        else:
            document.last_error = None
            document.set_status(DocumentStatus.DONE)
        db.commit()

        log_json(
            20,
            "ingest_upload_status",
            document_id=document.id,
            store_id=store.id,
            status=document.status.value,
        )

        if document.status == DocumentStatus.DONE:
            _log_index_cost(store, document, session_factory=session_factory)

    except Exception as exc:
        log_json(
            40,
            "ingest_unhandled_error",
            document_id=document_id,
            store_id=getattr(store, "id", None),
            op_name=op_name,
            **redact_llm_error(exc),
        )
        if uploaded_file_id and rag and store and document:
            try:
                rag.delete_document_from_store(store.fs_name, document.id, document.filename, file_id=uploaded_file_id)
                log_json(
                    20,
                    "ingest_upload_rollback_deleted_remote",
                    document_id=document.id,
                    store_id=store.id,
                    file_id=uploaded_file_id,
                )
            except Exception as cleanup_exc:  # pragma: no cover - best effort cleanup
                logger.warning(
                    "Failed to delete remote file after ingestion rollback",
                    exc_info=cleanup_exc,
                    extra={"document_id": document.id, "store_id": store.id, "file_id": uploaded_file_id},
                )
        if document:
            document.last_error = _sanitize_error(exc)
            document.set_status(DocumentStatus.ERROR)
            db.commit()
    finally:
        _cleanup_temp_file(local_path)
        db.close()


async def index_document_job(
    ctx: Any, store_id: int, document_id: int, local_path: str, session_factory: SessionFactory | None = None
) -> None:
    """ARQ job wrapper: run sync ingestion logic in a worker thread."""
    await asyncio.to_thread(run_ingestion_sync, store_id, document_id, local_path, session_factory or SessionLocal)
