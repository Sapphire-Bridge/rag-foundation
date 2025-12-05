# SPDX-License-Identifier: Apache-2.0

"""Utility helpers for admin audit logging."""

from __future__ import annotations

import json
from typing import Any
from sqlalchemy.orm import Session
from ..models import AdminAuditLog
from ..telemetry import log_json


def record_admin_action(
    db: Session,
    *,
    admin_user_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AdminAuditLog:
    entry = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        metadata_json=json.dumps(metadata or {}),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log_json(
        20,
        "admin_audit_log",
        admin_user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
    )
    return entry
