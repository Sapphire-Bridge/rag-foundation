# SPDX-License-Identifier: Apache-2.0

import os
import re
import uuid

import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..costs import (
    acquire_budget_lock,
    calc_index_cost,
    estimate_tokens_from_bytes,
    require_pricing_configured,
    would_exceed_budget,
)
from ..db import get_db
from ..models import Document, DocumentStatus
from ..rate_limit import check_rate_limit
from ..schemas import OpStatus, UploadResponse
from ..security.tenant import require_document_owned_by_user, require_store_owned_by_user
from ..services.gemini_rag import get_rag_client
from ..services.storage import upload_to_gcs_archive
from ..telemetry import log_json
from ..worker import enqueue_ingestion_job, has_ingestion_queue

router = APIRouter(prefix="/upload", tags=["upload"])
logger = logging.getLogger(__name__)

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_name(name: str, max_len: int = 128) -> str:
    name = os.path.basename(name)
    name = name.strip().replace(" ", "_")
    name = SAFE_NAME_RE.sub("_", name)
    name = name.lstrip(".")[:max_len] or "file"
    return name


# MIME types that require stricter magic-number validation
MAGIC_CHECKED_MIMES: set[str] = {
    "application/pdf",
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
}

ZIP_BASED_MIMES: set[str] = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
}


def allowed_type(file: UploadFile) -> bool:
    """Validate file type using the configured allow-list."""
    ct = (file.content_type or "").lower().split(";")[0].strip()
    return ct in settings.ALLOWED_UPLOAD_MIMES


def validate_file_magic(path: str, mime: str) -> bool:
    """
    Strengthen validation for binary document formats by checking headers.
    """
    mime = mime.lower()
    try:
        with open(path, "rb") as f:
            header = f.read(8)

        if mime == "application/pdf":
            if not header or not header.startswith(b"%PDF-"):
                return False

            # Also check for PDF EOF marker (%%EOF near end of file)
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(size - 2048, 0), os.SEEK_SET)
                tail = f.read()

            return b"%%EOF" in tail

        if mime in ZIP_BASED_MIMES:
            if not header or not header.startswith(b"PK\x03\x04"):
                return False

            return True

        # For other types we currently skip strict magic checks
        if not header:
            return False

        return True
    except Exception:
        return False


@router.post("", response_model=UploadResponse)
async def upload(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_pricing_configured),
    storeId: int = Form(..., description="ID of the target store"),
    file: UploadFile = File(..., description="Document file to ingest"),
    displayName: str | None = Form(None, max_length=255, description="Optional display name override"),
):
    # Ensure we return 401 before validating the payload when auth is missing.
    authz = request.headers.get("authorization")
    if not authz or not authz.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    if storeId is None or file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing storeId or file")
    # Per-user rate limit (additional to global middleware)
    check_rate_limit(f"user:{user.id}:upload", settings.UPLOAD_RATE_LIMIT_PER_MINUTE)

    # Structured audit log for troubleshooting uploads
    ct = (file.content_type or "").lower()
    normalized_ct = ct.split(";")[0].strip()
    try:
        log_json(20, "upload_request", user_id=user.id, store_id=storeId, filename=file.filename, content_type=ct)
    except Exception:
        pass
    store = require_store_owned_by_user(db, storeId, user.id)

    if not allowed_type(file):
        normalized_display = normalized_ct or "unknown"
        allowed_list = ", ".join(settings.ALLOWED_UPLOAD_MIMES)
        log_json(
            30,
            "upload_invalid_mime",
            user_id=user.id,
            store_id=storeId,
            filename=file.filename,
            content_type=file.content_type,
        )
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported media type '{normalized_display}'. "
                f"Allowed types (profile={settings.UPLOAD_PROFILE}): {allowed_list}"
            ),
        )

    # Enforce size cap while streaming to temp with secure file creation
    os.makedirs(settings.TMP_DIR, exist_ok=True, mode=0o700)
    safe_name = sanitize_name(file.filename or "file")

    # Use tempfile.mkstemp for secure, unique temp file creation
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    tmp_path = os.path.join(settings.TMP_DIR, unique_name)

    # Create file with restrictive permissions (owner read/write only)
    fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)

    size = 0
    try:
        with os.fdopen(fd, "wb") as w:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
                    log_json(30, "upload_too_large", user_id=user.id, store_id=storeId, size_bytes=size)
                    try:
                        os.remove(tmp_path)
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        logging.warning("Failed to remove temp file %s: %s", tmp_path, exc)
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
                w.write(chunk)
    except Exception:
        # Clean up on error
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logging.warning("Failed to remove temp file %s: %s", tmp_path, exc)
        raise

    # Validate file magic numbers after save
    content_type = normalized_ct
    if content_type and content_type in MAGIC_CHECKED_MIMES:
        if not validate_file_magic(tmp_path, content_type):
            log_json(30, "upload_magic_mismatch", user_id=user.id, store_id=storeId, filename=file.filename)
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logging.warning("Failed to remove temp file %s: %s", tmp_path, exc)
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File content does not match declared type"
            )

    # Budget check based on estimated indexing tokens/cost
    est_tokens = estimate_tokens_from_bytes(size, content_type)
    idx_result = calc_index_cost(est_tokens)
    idx_cost = idx_result.total_cost_usd
    if idx_cost > 0:
        acquire_budget_lock(db, user.id)
        if would_exceed_budget(db, user.id, idx_cost):
            log_json(
                30, "upload_budget_exceeded", user_id=user.id, store_id=storeId, estimated_cost_usd=float(idx_cost)
            )
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logging.warning("Failed to remove temp file %s: %s", tmp_path, exc)
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Monthly budget exceeded")

    doc = Document(
        store_id=store.id, filename=safe_name, display_name=displayName, size_bytes=size, status=DocumentStatus.PENDING
    )
    db.add(doc)
    db.flush()

    # Commit before scheduling background task so the worker can load the document in a new session
    db.commit()
    db.refresh(doc)

    gcs_uri = None
    if settings.GCS_ARCHIVE_BUCKET:
        try:
            gcs_uri = upload_to_gcs_archive(tmp_path, store_id=store.id, document_id=doc.id, filename=safe_name)
        except Exception as exc:
            logger.warning("Failed to upload archive copy to GCS", exc_info=exc, extra={"document_id": doc.id})
    if gcs_uri:
        if len(gcs_uri) > 512:
            logger.warning(
                "Archive URI too long; truncating to column limit",
                extra={"document_id": doc.id, "length": len(gcs_uri)},
            )
            gcs_uri = gcs_uri[:512]
        doc.gcs_uri = gcs_uri
        db.add(doc)
        db.commit()
        db.refresh(doc)

    enqueue_error: Exception | None = None
    if has_ingestion_queue():
        try:
            await enqueue_ingestion_job(store.id, doc.id, tmp_path)
        except Exception as exc:
            enqueue_error = exc
    else:
        enqueue_error = RuntimeError("Ingestion queue unavailable")

    if enqueue_error:
        log_json(
            30,
            "upload_ingestion_queue_unavailable",
            user_id=user.id,
            store_id=store.id,
            document_id=doc.id,
            error=str(enqueue_error),
        )
        doc.set_status(DocumentStatus.ERROR)
        db.add(doc)
        db.commit()
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logging.warning("Failed to remove temp file %s: %s", tmp_path, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion service busy/unavailable. Please try again later.",
        )
    else:
        log_json(
            20, "upload_enqueued", user_id=user.id, store_id=storeId, document_id=doc.id, size_bytes=size, queue="redis"
        )

    return UploadResponse(
        op_id=f"doc-{doc.id}",
        document_id=doc.id,
        file_display_name=displayName or safe_name,
        estimated_tokens=idx_result.tokens,
        estimated_cost_usd=float(idx_cost),
    )


@router.get("/op-status/{op_id}", response_model=OpStatus)
def op_status(op_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # We use "doc-{id}" as op_id
    if not op_id.startswith("doc-"):
        log_json(30, "op_status_invalid_id", user_id=user.id, op_id=op_id)
        raise HTTPException(status_code=400, detail="Invalid op id")
    try:
        doc_id = int(op_id.split("-", 1)[1])
    except (ValueError, IndexError):
        log_json(30, "op_status_parse_error", user_id=user.id, op_id=op_id)
        raise HTTPException(status_code=400, detail="Invalid op id format")
    doc = require_document_owned_by_user(db, doc_id, user.id)

    if doc.status in (DocumentStatus.DONE, DocumentStatus.ERROR):
        err = None
        if doc.status == DocumentStatus.ERROR:
            reason = doc.last_error or "Indexing error"
            err = f"Indexing failed: {reason}"
        return OpStatus(
            status=doc.status,
            error=err,
        )

    # If running, try to read remote status best-effort
    if doc.op_name:
        rag = get_rag_client()
        try:
            st = rag.op_status(doc.op_name)
        except Exception as exc:
            log_json(
                30,
                "op_status_failed",
                user_id=user.id,
                document_id=doc.id,
                op_name=doc.op_name,
                error=str(exc),
            )
            return OpStatus(status=DocumentStatus.RUNNING, error="Status check failed; retrying")
        if st.get("error"):
            # Mark ERROR to expose failure; if Gemini finishes later, a subsequent poll can flip to DONE.
            doc.set_status(DocumentStatus.ERROR)
            db.add(doc)
        elif st.get("done"):
            doc.set_status(DocumentStatus.DONE)
            db.add(doc)
        else:
            logger.debug(
                "Ingestion operation still running",
                extra={"document_id": doc.id, "op_name": st.get("name")},
            )
        db.commit()
        response_status = doc.status
        if doc.status == DocumentStatus.PENDING:
            # UX: surface initial PENDING as RUNNING so clients see progress immediately.
            response_status = DocumentStatus.RUNNING
        return OpStatus(status=response_status, error=st.get("error"))
    return OpStatus(status=doc.status, error=None)
