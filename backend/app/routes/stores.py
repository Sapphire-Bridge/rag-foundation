from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx
from ..genai import errors as gemini_errors
from ..schemas import StoreCreate, StoreOut
from ..services.gemini_rag import get_rag_client
from ..services.cleanup import enqueue_store_cleanup
from ..config import settings
from ..rate_limit import check_rate_limit
from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import Store, Document, User
from ..security.tenant import require_store_owned_by_user
from ..services.audit import record_admin_action
from ..telemetry import log_json

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreOut])
def list_stores(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[StoreOut]:
    rows = db.query(Store).filter(Store.user_id == user.id, Store.deleted_at.is_(None)).order_by(Store.id.desc()).all()
    return [StoreOut(id=r.id, display_name=r.display_name, fs_name=r.fs_name) for r in rows]


@router.post("", response_model=StoreOut)
def create_store(body: StoreCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> StoreOut:
    store_count = db.query(Store).filter(Store.user_id == user.id, Store.deleted_at.is_(None)).count()
    if store_count >= settings.MAX_STORES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {settings.MAX_STORES_PER_USER} stores per user",
        )

    rag = get_rag_client()
    try:
        fs_name = rag.create_store(body.display_name)
    except (gemini_errors.APIError, httpx.TimeoutException, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API is currently unreachable; please retry shortly.",
        ) from exc

    if not isinstance(fs_name, str) or not (fs_name.startswith("corpora/") or fs_name.startswith("fileSearchStores/")):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Store creation failed: invalid store name format",
        )

    existing = db.query(Store).filter(Store.fs_name == fs_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Store with this name already exists",
        )

    store = Store(user_id=user.id, display_name=body.display_name, fs_name=fs_name)
    db.add(store)
    db.commit()
    db.refresh(store)
    return StoreOut(id=store.id, display_name=store.display_name, fs_name=store.fs_name)


@router.delete("/{store_id}", status_code=status.HTTP_202_ACCEPTED)
def delete_store(
    store_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    store = require_store_owned_by_user(db, store_id, user.id)

    deleted_at = store.soft_delete(user_id=user.id)
    db.query(Document).filter(
        Document.store_id == store.id,
        Document.deleted_at.is_(None),
    ).update({"deleted_at": deleted_at, "deleted_by": user.id}, synchronize_session=False)
    db.commit()

    enqueue_store_cleanup(background, store_id=store.id, store_fs_name=store.fs_name)
    log_json(
        20,
        "store_soft_deleted",
        user_id=user.id,
        store_id=store.id,
    )
    return {"status": "deletion_scheduled"}


@router.post("/{store_id}/restore", response_model=StoreOut)
def restore_store(
    store_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> StoreOut:
    check_rate_limit(f"admin:{getattr(admin_user, 'id', 'unknown')}:restore_store", settings.RATE_LIMIT_PER_MINUTE)
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")

    store.restore()
    db.query(Document).filter(Document.store_id == store.id).update(
        {"deleted_at": None, "deleted_by": None},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(store)

    record_admin_action(
        db,
        admin_user_id=getattr(admin_user, "id", None),
        action="restore_store",
        target_type="store",
        target_id=str(store.id),
    )
    log_json(20, "store_restored", store_id=store.id, admin_id=getattr(admin_user, "id", None))
    return StoreOut(id=store.id, display_name=store.display_name, fs_name=store.fs_name)
