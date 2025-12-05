from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import AppSetting, User
from ..schemas import AppSettings, AppSettingsUpdate
from ..services.audit import record_admin_action
from ..telemetry import log_json
from ..rate_limit import check_rate_limit
from ..config import settings

router = APIRouter(tags=["settings"])

DEFAULT_SETTINGS = AppSettings().model_dump()
SETTING_MAX_LENGTHS: dict[str, int] = {
    "app_favicon": 200_000,
}
DEFAULT_SETTING_MAX_LENGTH = 255
VALID_ICONS = {"sparkles", "file", "bot", "book", "bolt", "compass"}
VALID_PRESETS = {"minimal", "gradient", "classic"}
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _load_settings(db: Session) -> AppSettings:
    merged = dict(DEFAULT_SETTINGS)
    rows = db.query(AppSetting).all()
    for row in rows:
        merged[row.key] = row.value
    return AppSettings(**merged)


@router.get("/settings", response_model=AppSettings)
def read_settings(db: Session = Depends(get_db)) -> AppSettings:
    return _load_settings(db)


@router.post("/settings", response_model=AppSettings)
def update_settings(
    payload: AppSettingsUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> AppSettings:
    check_rate_limit(f"admin:{admin_user.id}:update_settings", settings.RATE_LIMIT_PER_MINUTE)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return _load_settings(db)

    for key, value in updates.items():
        if key not in DEFAULT_SETTINGS:
            raise HTTPException(status_code=400, detail=f"Unknown setting: {key}")
        value_str = value.strip() if isinstance(value, str) else str(value)
        if key in {"primary_color", "accent_color"} and not HEX_COLOR_RE.match(value_str):
            raise HTTPException(status_code=400, detail=f"{key} must be a 6-digit hex color (e.g., #2563EB)")
        if key == "app_icon" and value_str not in VALID_ICONS:
            raise HTTPException(status_code=400, detail=f"app_icon must be one of: {', '.join(sorted(VALID_ICONS))}")
        if key == "theme_preset" and value_str not in VALID_PRESETS:
            raise HTTPException(
                status_code=400, detail=f"theme_preset must be one of: {', '.join(sorted(VALID_PRESETS))}"
            )
        max_len = SETTING_MAX_LENGTHS.get(key, DEFAULT_SETTING_MAX_LENGTH)
        if len(value_str) > max_len:
            raise HTTPException(status_code=400, detail=f"Setting {key} is too long (max {max_len} chars)")

        existing = db.get(AppSetting, key)
        if existing:
            existing.value = value_str
        else:
            db.add(AppSetting(key=key, value=value_str))

    db.commit()

    record_admin_action(
        db,
        admin_user_id=admin_user.id,
        action="update_settings",
        target_type="settings",
        target_id=None,
        metadata=updates,
    )
    log_json(20, "admin_update_settings", admin_id=admin_user.id, keys=list(updates.keys()))

    return _load_settings(db)
