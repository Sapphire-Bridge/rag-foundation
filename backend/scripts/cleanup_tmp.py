# SPDX-License-Identifier: Apache-2.0
"""
Delete temporary upload files older than TMP_MAX_AGE_HOURS.

Run inside the backend container (working dir /app/backend) via:
    python -m scripts.cleanup_tmp
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def cleanup_tmp(tmp_dir: str | Path | None = None, max_age_hours: int | None = None) -> int:
    tmp_dir = Path(tmp_dir or settings.TMP_DIR)
    max_age_hours = max_age_hours if max_age_hours is not None else settings.TMP_MAX_AGE_HOURS
    if max_age_hours <= 0:
        logger.info("TMP_MAX_AGE_HOURS <= 0; skipping cleanup.")
        return 0

    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    if not tmp_dir.exists():
        return removed

    for entry in tmp_dir.iterdir():
        try:
            if not entry.is_file():
                continue
            mtime = entry.stat().st_mtime
            if mtime < cutoff:
                entry.unlink(missing_ok=True)
                removed += 1
        except Exception as exc:
            logger.warning("Failed to inspect/remove %s: %s", entry, exc)
    return removed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    deleted = cleanup_tmp()
    logger.info("Removed %s stale temp file(s) from %s", deleted, settings.TMP_DIR)
