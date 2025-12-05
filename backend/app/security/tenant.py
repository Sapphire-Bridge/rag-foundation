# SPDX-License-Identifier: Apache-2.0

from typing import Iterable, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Document, Store
from app.telemetry import log_json


def require_store_owned_by_user(db: Session, store_id: int, user_id: int) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.user_id == user_id,
            Store.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if store is None:
        log_json(30, "store_access_denied", user_id=user_id, store_id=store_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return store


def require_stores_owned_by_user(db: Session, store_ids: Iterable[int], user_id: int) -> List[Store]:
    ids = list(store_ids)
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing storeIds")

    stores = (
        db.query(Store)
        .filter(
            Store.id.in_(ids),
            Store.user_id == user_id,
            Store.deleted_at.is_(None),
        )
        .all()
    )
    found_ids = {s.id for s in stores}
    missing = [sid for sid in ids if sid not in found_ids]
    if missing:
        log_json(30, "store_access_denied", user_id=user_id, store_ids=missing)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return stores


def require_document_owned_by_user(db: Session, document_id: int, user_id: int) -> Document:
    doc = (
        db.query(Document)
        .join(Store, Document.store_id == Store.id)
        .filter(
            Document.id == document_id,
            Store.user_id == user_id,
            Store.deleted_at.is_(None),
            Document.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if doc is None:
        log_json(30, "document_access_denied", user_id=user_id, document_id=document_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc
