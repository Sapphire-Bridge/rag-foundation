from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user
from app.config import settings
from app.db import SessionLocal
from app.models import Store
import app.routes.uploads as uploads_routes


def test_upload_requires_auth():
    c = TestClient(app)
    r = c.post("/api/upload", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 401


@pytest.fixture()
def authed_client():
    """Provide a client with a mocked authenticated user."""
    client = TestClient(app)
    user = SimpleNamespace(id=123)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield client, user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def store_record(authed_client):
    """Create a store for the mocked user."""
    _, user = authed_client
    session = SessionLocal()
    store = Store(
        user_id=user.id,
        display_name="Test Store",
        fs_name=f"stores/test-{uuid.uuid4().hex}",
    )
    session.add(store)
    session.commit()
    session.refresh(store)
    try:
        yield store
    finally:
        session.close()


@pytest.fixture(autouse=True)
def restore_upload_settings():
    """Ensure ALLOWED_UPLOAD_MIMES resets after each test."""
    original_profile = settings.UPLOAD_PROFILE
    original_mimes = list(settings.ALLOWED_UPLOAD_MIMES)
    yield
    settings.UPLOAD_PROFILE = original_profile
    settings.ALLOWED_UPLOAD_MIMES = original_mimes


def _headers():
    return {"Authorization": "Bearer test", "X-Requested-With": "XMLHttpRequest"}


def test_upload_rejects_disallowed_mime(authed_client, store_record):
    client, _ = authed_client
    store = store_record
    settings.ALLOWED_UPLOAD_MIMES = ["application/pdf"]
    resp = client.post(
        "/api/upload",
        data={"storeId": str(store.id)},
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=_headers(),
    )
    assert resp.status_code == 415


def test_upload_accepts_excel_when_allowed(authed_client, store_record):
    client, _ = authed_client
    store = store_record
    settings.ALLOWED_UPLOAD_MIMES = ["application/vnd.ms-excel"]
    file_bytes = b"PK\x03\x04" + b"x" * 1000
    # Ensure ingestion queue path succeeds in tests
    original_has_queue = uploads_routes.has_ingestion_queue
    original_enqueue = uploads_routes.enqueue_ingestion_job
    uploads_routes.has_ingestion_queue = lambda: True

    async def _noop_enqueue(store_id, doc_id, tmp_path):
        return None

    uploads_routes.enqueue_ingestion_job = _noop_enqueue
    try:
        resp = client.post(
            "/api/upload",
            data={"storeId": str(store.id)},
            files={
                "file": (
                    "sheet.xls",
                    io.BytesIO(file_bytes),
                    "application/vnd.ms-excel",
                )
            },
            headers=_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("estimated_tokens", 0) > 0
        assert body.get("estimated_cost_usd", 0) > 0
    finally:
        uploads_routes.has_ingestion_queue = original_has_queue
        uploads_routes.enqueue_ingestion_job = original_enqueue


def test_pdf_magic_mismatch_is_rejected(authed_client, store_record):
    client, _ = authed_client
    store = store_record
    settings.ALLOWED_UPLOAD_MIMES = ["application/pdf"]
    resp = client.post(
        "/api/upload",
        data={"storeId": str(store.id)},
        files={"file": ("fake.pdf", b"not-a-pdf-content", "application/pdf")},
        headers=_headers(),
    )
    assert resp.status_code == 415
