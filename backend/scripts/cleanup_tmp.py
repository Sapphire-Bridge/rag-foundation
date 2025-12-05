#!/usr/bin/env python
"""
Remove stale temp upload files to keep disk usage bounded.
"""

import time
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.models import Document, DocumentStatus
from app.telemetry import setup_logging

logger = setup_logging()


def _active_docs(session):
    return {d.id for d in session.query(Document.id).filter(Document.status == DocumentStatus.RUNNING).all()}


def main() -> None:
    tmpdir = Path(settings.TMP_DIR)
    if not tmpdir.exists():
        logger.info("TMP_DIR missing; nothing to clean", extra={"tmp_dir": str(tmpdir)})
        return

    cutoff = time.time() - (settings.TMP_MAX_AGE_HOURS * 3600)
    session = SessionLocal()
    active = _active_docs(session)
    removed = 0

    for path in tmpdir.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime > cutoff:
                continue
            path.unlink()
            removed += 1
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.warning("Failed to remove temp file", extra={"path": str(path), "error": str(exc)})

    session.close()
    logger.info("Temp cleanup complete", extra={"removed": removed, "active_running_docs": len(active)})


if __name__ == "__main__":
    main()
