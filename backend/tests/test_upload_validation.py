from __future__ import annotations

import io
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.auth import get_current_user
from app.config import settings
from app.models import Store, User, Budget
import app.routes.uploads as uploads_routes


def test_upload_requires_auth(client):
    r = client.post("/api/upload", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 401


@pytest.fixture()
def authed_client(client):
    """Provide a client with a mocked authenticated user."""
    user = SimpleNamespace(id=123)
    client.app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield client, user
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def store_record(authed_client, db_session):
    """Create a store for the mocked user."""
    _, user = authed_client
    # Ensure owning user exists for FK integrity
    db_user = db_session.get(User, user.id)
    if db_user is None:
        db_user = User(
            id=user.id,
            email=f"user-{user.id}@example.com",
            hashed_password="",
            is_active=True,
            email_verified=True,
        )
        db_session.add(db_user)
        db_session.commit()

    store = Store(
        user_id=user.id,
        display_name="Test Store",
        fs_name=f"stores/test-{uuid.uuid4().hex}",
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


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


def test_upload_budget_hold_blocks_when_near_limit(client, db_session):
    unique_email = f"budget+{uuid.uuid4().hex}@example.com"
    user = User(email=unique_email, hashed_password="", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    budget = Budget(user_id=user.id, monthly_limit_usd=Decimal("0.03"))
    db_session.add(budget)
    store = Store(user_id=user.id, display_name="Budget Store", fs_name=f"stores/test-{uuid.uuid4().hex}")
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)

    original_price = settings.PRICE_PER_MTOK_INDEX
    original_hold = settings.BUDGET_HOLD_USD
    settings.PRICE_PER_MTOK_INDEX = 1.0  # magnify cost to trigger hold logic
    settings.BUDGET_HOLD_USD = 0.02

    original_calc = uploads_routes.calc_index_cost

    class _IdxResult:
        def __init__(self, cost: Decimal):
            self.total_cost_usd = cost

    def _fake_calc_index_cost(tokens: int, model: str | None = None):
        return _IdxResult(Decimal("0.015"))

    uploads_routes.calc_index_cost = _fake_calc_index_cost
    client.app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = client.post(
            "/api/upload",
            data={"storeId": str(store.id)},
            files={"file": ("big.txt", b"x" * 200000, "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 402
    finally:
        settings.PRICE_PER_MTOK_INDEX = original_price
        settings.BUDGET_HOLD_USD = original_hold
        uploads_routes.calc_index_cost = original_calc
        client.app.dependency_overrides.pop(get_current_user, None)
