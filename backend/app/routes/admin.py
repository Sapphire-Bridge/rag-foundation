from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func
from pydantic import BaseModel

from ..auth import require_admin
from ..db import get_db
from ..models import User, Budget, AdminAuditLog, Document, Store, DocumentStatus
from ..schemas import (
    AdminUserOut,
    AdminUserRoleUpdate,
    BudgetUpdate,
    AdminAuditEntry,
    AdminSystemSummary,
    WatchdogResetResponse,
    DeletionAuditEntry,
)
from ..services.audit import record_admin_action
from ..telemetry import log_json
from ..rate_limit import check_rate_limit
from ..config import settings


router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_rate_limit(admin_user: User, action: str) -> None:
    check_rate_limit(f"admin:{admin_user.id}:{action}", settings.RATE_LIMIT_PER_MINUTE)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
    limit: int = Query(100, ge=1, le=500),
) -> list[AdminUserOut]:
    _admin_rate_limit(admin_user, "list_users")
    rows = db.query(User).options(joinedload(User.budget)).order_by(User.id.desc()).limit(limit).all()
    return [
        AdminUserOut(
            id=row.id,
            email=row.email,
            is_admin=row.is_admin,
            is_active=row.is_active,
            admin_notes=row.admin_notes,
            monthly_limit_usd=float(row.budget.monthly_limit_usd) if row.budget else None,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/users/{user_id}/role", response_model=AdminUserOut)
def set_user_role(
    user_id: int,
    payload: AdminUserRoleUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> AdminUserOut:
    _admin_rate_limit(admin_user, "set_user_role")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if admin_user.id == user_id and admin_user.is_admin and not payload.is_admin:
        raise HTTPException(
            status_code=400,
            detail="Admins cannot remove their own admin access",
        )

    target.is_admin = payload.is_admin
    target.admin_notes = payload.admin_notes
    db.commit()
    db.refresh(target)

    record_admin_action(
        db,
        admin_user_id=admin_user.id,
        action="set_user_role",
        target_type="user",
        target_id=str(user_id),
        metadata={"is_admin": payload.is_admin},
    )

    log_json(20, "admin_set_user_role", admin_id=admin_user.id, target_user_id=user_id, is_admin=payload.is_admin)
    return AdminUserOut(
        id=target.id,
        email=target.email,
        is_admin=target.is_admin,
        is_active=target.is_active,
        admin_notes=target.admin_notes,
        created_at=target.created_at,
    )


@router.post("/budgets/{user_id}", response_model=BudgetUpdate)
def upsert_budget(
    user_id: int,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> BudgetUpdate:
    _admin_rate_limit(admin_user, "set_budget")
    limit_dec = Decimal(str(payload.monthly_limit_usd))
    limit = float(limit_dec)
    budget = db.query(Budget).filter(Budget.user_id == user_id).one_or_none()
    if budget:
        budget.monthly_limit_usd = limit_dec
    else:
        budget = Budget(user_id=user_id, monthly_limit_usd=limit_dec)
        db.add(budget)
    db.commit()

    record_admin_action(
        db,
        admin_user_id=admin_user.id,
        action="set_budget",
        target_type="user",
        target_id=str(user_id),
        metadata={"monthly_limit_usd": limit},
    )
    log_json(20, "admin_set_budget", admin_id=admin_user.id, target_user_id=user_id, monthly_limit=limit)
    return BudgetUpdate(monthly_limit_usd=limit)


@router.get("/audit", response_model=list[AdminAuditEntry])
def list_audit_logs(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
) -> list[AdminAuditEntry]:
    _admin_rate_limit(admin_user, "list_audit")
    rows = db.query(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(limit).all()
    return [
        AdminAuditEntry(
            id=row.id,
            admin_user_id=row.admin_user_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            metadata_json=row.metadata_json,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/system/summary", response_model=AdminSystemSummary)
def system_summary(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> AdminSystemSummary:
    _admin_rate_limit(admin_user, "system_summary")
    user_count = db.query(func.count(User.id)).scalar() or 0
    store_count = db.query(func.count(Store.id)).scalar() or 0
    doc_count = db.query(func.count(Document.id)).scalar() or 0
    log_json(20, "admin_system_summary", admin_id=admin_user.id)
    return AdminSystemSummary(
        users=user_count,
        stores=store_count,
        documents=doc_count,
    )


class WatchdogResetRequest(BaseModel):
    user_id: Optional[int] = None
    ttl_minutes: int = 30


@router.post("/watchdog/reset-stuck", response_model=WatchdogResetResponse)
def admin_reset_stuck(
    body: WatchdogResetRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> WatchdogResetResponse:
    _admin_rate_limit(admin_user, "watchdog_reset")
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=body.ttl_minutes)
    query = (
        db.query(Document)
        .join(Store)
        .filter(
            and_(
                Document.status == DocumentStatus.RUNNING,
                func.coalesce(Document.status_updated_at, Document.created_at) < cutoff,
                Store.deleted_at.is_(None),
                Document.deleted_at.is_(None),
            )
        )
    )
    if body.user_id:
        query = query.filter(Store.user_id == body.user_id)

    docs = query.all()
    count = 0
    for doc in docs:
        doc.set_status(DocumentStatus.PENDING)
        doc.op_name = None
        count += 1

    db.commit()

    record_admin_action(
        db,
        admin_user_id=admin_user.id,
        action="watchdog_reset",
        target_type="document",
        target_id=None,
        metadata={
            "reset_count": count,
            "ttl_minutes": body.ttl_minutes,
            "target_user_id": body.user_id,
        },
    )
    log_json(
        20,
        "admin_watchdog_reset",
        admin_id=admin_user.id,
        reset_count=count,
        ttl_minutes=body.ttl_minutes,
        target_user_id=body.user_id,
    )
    return WatchdogResetResponse(reset_count=count)


@router.get("/audit/deletions", response_model=list[DeletionAuditEntry])
def get_deletion_audit(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[DeletionAuditEntry]:
    _admin_rate_limit(admin_user, "deletion_audit")
    deleted_stores = (
        db.query(Store).filter(Store.deleted_at.isnot(None)).options(joinedload(Store.deleted_by_user)).all()
    )

    out: list[DeletionAuditEntry] = []
    for store in deleted_stores:
        deleted_at = store.deleted_at
        if deleted_at is None:
            continue
        out.append(
            DeletionAuditEntry(
                store_id=store.id,
                deleted_at=deleted_at,
                deleted_by=store.deleted_by_user.email if store.deleted_by_user else None,
            )
        )
    return out
