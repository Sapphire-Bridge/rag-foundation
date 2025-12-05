"""Template for admin-only mutation endpoints.

Copy and modify this string for new admin operations.
Keep the audit call mandatory for any admin mutation.
"""

from __future__ import annotations

ADMIN_ENDPOINT_TEMPLATE = """\
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import Resource  # replace with your model
from ..services.audit import record_admin_action
from ..telemetry import log_json

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("/{resource_id}/action")
def admin_action_resource(
    resource_id: int,
    admin_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 1. Fetch resource
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

    # 2. Perform action
    resource.state = "new_state"
    db.commit()
    db.refresh(resource)

    # 3. Audit (REQUIRED for admin mutations)
    record_admin_action(
        db,
        admin_user_id=getattr(admin_user, "id", None),
        action="action_resource",
        target_type="resource",
        target_id=resource.id,
        metadata={"state": resource.state},
    )

    # 4. Log
    log_json(20, "admin_action_resource", admin_id=getattr(admin_user, "id", None), resource_id=resource_id)

    return resource
"""
