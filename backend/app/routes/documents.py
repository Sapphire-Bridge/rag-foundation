from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import Document, User
from ..schemas import DocumentOut
from ..security.tenant import require_document_owned_by_user, require_store_owned_by_user
from ..services.cleanup import enqueue_document_cleanup
from ..services.audit import record_admin_action
from ..telemetry import log_json
from ..rate_limit import check_rate_limit
from ..config import settings

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/store/{store_id}", response_model=list[DocumentOut])
def list_documents_for_store(
    store_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentOut]:
    require_store_owned_by_user(db, store_id, user.id)
    docs = (
        db.query(Document)
        .filter(Document.store_id == store_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        DocumentOut(
            id=d.id,
            store_id=d.store_id,
            filename=d.filename,
            display_name=d.display_name,
            status=d.status,
            size_bytes=d.size_bytes,
            created_at=d.created_at,
            gcs_uri=getattr(d, "gcs_uri", None),
        )
        for d in docs
    ]


@router.delete("/{document_id}", status_code=status.HTTP_202_ACCEPTED)
def delete_document(
    document_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    document = require_document_owned_by_user(db, document_id, user.id)

    document.soft_delete(user_id=user.id)
    db.commit()

    enqueue_document_cleanup(background, document_id=document.id)
    log_json(20, "document_soft_deleted", user_id=user.id, document_id=document.id, store_id=document.store_id)
    return {"status": "deletion_scheduled"}


@router.post("/{document_id}/restore")
def restore_document(
    document_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> dict[str, int]:
    check_rate_limit(f"admin:{getattr(admin_user, 'id', 'unknown')}:restore_document", settings.RATE_LIMIT_PER_MINUTE)
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    document.restore()
    db.commit()

    record_admin_action(
        db,
        admin_user_id=getattr(admin_user, "id", None),
        action="restore_document",
        target_type="document",
        target_id=str(document.id),
        metadata={"store_id": document.store_id},
    )
    log_json(
        20,
        "document_restored",
        document_id=document.id,
        store_id=document.store_id,
        admin_id=getattr(admin_user, "id", None),
    )
    return {"document_id": document.id, "store_id": document.store_id}
