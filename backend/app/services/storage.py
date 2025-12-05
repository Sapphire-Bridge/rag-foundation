# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from typing import Optional

from app.config import settings


def _require_storage_client():
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "google-cloud-storage is required for GCS archiving. Install it or disable GCS_ARCHIVE_BUCKET."
        ) from exc
    return storage.Client()


def upload_to_gcs_archive(local_path: str, *, store_id: int, document_id: int, filename: str) -> Optional[str]:
    """
    Upload the local temp file to a GCS bucket for long-term retention.
    """
    bucket_name = settings.GCS_ARCHIVE_BUCKET
    if not bucket_name:
        return None

    client = _require_storage_client()
    bucket = client.bucket(bucket_name)

    _, ext = os.path.splitext(filename)
    blob_name = f"{store_id}/{document_id}{ext or ''}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)

    return f"gs://{bucket_name}/{blob_name}"
