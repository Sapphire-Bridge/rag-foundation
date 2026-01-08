import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_upload_path_matching_skips_body_limit_for_real_upload_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure the request body limiter treats only /api/upload and /api/upload/... as uploads.
    """
    monkeypatch.setattr(settings, "MAX_JSON_MB", 0)
    client = TestClient(app)

    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Length": "1",
        "X-Requested-With": "XMLHttpRequest",
    }

    # Non-upload prefixes should not be exempt.
    assert client.post("/api/upload-op", content=b"x", headers=headers).status_code == 413
    assert client.post("/api/uploading", content=b"x", headers=headers).status_code == 413

    # Upload endpoints (and nested paths) should be exempt from the global JSON/body-size guard.
    assert client.post("/api/upload", content=b"x", headers=headers).status_code != 413
    assert client.post("/api/upload/op-status/xyz", content=b"x", headers=headers).status_code != 413
