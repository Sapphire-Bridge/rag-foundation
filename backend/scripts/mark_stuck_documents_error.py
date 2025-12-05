# SPDX-License-Identifier: Apache-2.0
"""
Mark documents stuck in RUNNING as ERROR after a timeout window.

Usage:
    python -m scripts.mark_stuck_documents_error 60   # minutes, default=60

This is a safety valve for production operations if Gemini status polling leaves
documents in RUNNING indefinitely.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Document, DocumentStatus


def main() -> None:
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    db = SessionLocal()
    try:
        stuck = (
            db.query(Document)
            .filter(
                Document.status == DocumentStatus.RUNNING,
                Document.created_at < cutoff,
                Document.deleted_at.is_(None),
            )
            .all()
        )
        if not stuck:
            print("No stuck documents found.")
            return

        for doc in stuck:
            doc.status = DocumentStatus.ERROR
        db.commit()
        print(f"Marked {len(stuck)} document(s) as ERROR.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
