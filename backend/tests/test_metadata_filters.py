from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.routes.chat as chat_routes
from app.auth import get_authorization
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import QueryLog, Store


@pytest.fixture()
def user():
    return SimpleNamespace(id=4242)


@pytest.fixture()
def client(user, monkeypatch):
    app.dependency_overrides[get_authorization] = lambda: "test-token"
    monkeypatch.setattr(chat_routes, "get_current_user", lambda db=None, token=None: user)
    cl = TestClient(app)
    try:
        yield cl
    finally:
        app.dependency_overrides.pop(get_authorization, None)


@pytest.fixture()
def store(user):
    session = SessionLocal()
    store = Store(
        user_id=user.id,
        display_name="Metadata Store",
        fs_name=f"stores/meta-{uuid.uuid4().hex}",
    )
    session.add(store)
    session.commit()
    session.refresh(store)
    session.close()

    try:
        yield store
    finally:
        session = SessionLocal()
        try:
            session.query(QueryLog).filter(QueryLog.user_id == user.id).delete()
            session.query(Store).filter(Store.id == store.id).delete()
            session.commit()
        finally:
            session.close()


class _RecordingRag:
    def __init__(self):
        self.seen_filter = None

    def new_stream_ids(self):
        return ("msg-meta", "text-meta")

    def ask_stream(self, *, question, store_names, metadata_filter, model):
        self.seen_filter = metadata_filter

        def _gen():
            yield SimpleNamespace(
                text="hello",
                candidates=[
                    SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1))
                ],
                usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
            )

        return _gen()

    def extract_citations_from_response(self, resp):
        return []


def test_metadata_filters_rejected_when_disabled(client, store, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_METADATA_FILTERS", False)
    monkeypatch.setattr(settings, "METADATA_FILTER_ALLOWED_KEYS", ["tenant"])

    resp = client.post(
        "/api/chat",
        json={
            "question": "hello?",
            "storeIds": [store.id],
            "metadataFilter": {"tenant": "acme"},
        },
    )

    assert resp.status_code == 400
    assert "Metadata filters are disabled" in resp.json()["detail"]


def test_metadata_filters_require_allowlist(client, store, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_METADATA_FILTERS", True)
    monkeypatch.setattr(settings, "METADATA_FILTER_ALLOWED_KEYS", [])

    resp = client.post(
        "/api/chat",
        json={
            "question": "hello?",
            "storeIds": [store.id],
            "metadataFilter": {"tenant": "acme"},
        },
    )

    assert resp.status_code == 400
    assert "METADATA_FILTER_ALLOWED_KEYS" in resp.json()["detail"]


def test_metadata_filters_reject_complex_shapes(client, store, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_METADATA_FILTERS", True)
    monkeypatch.setattr(settings, "METADATA_FILTER_ALLOWED_KEYS", ["tenant"])

    resp = client.post(
        "/api/chat",
        json={
            "question": "hello?",
            "storeIds": [store.id],
            "metadataFilter": {"tenant": {"$gt": 1}},
        },
    )

    assert resp.status_code == 400
    assert "Invalid metadataFilter value" in resp.json()["detail"]


def test_metadata_filters_allow_allowlisted_scalars(client, store, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_METADATA_FILTERS", True)
    monkeypatch.setattr(settings, "METADATA_FILTER_ALLOWED_KEYS", ["tenant", "region"])

    rag = _RecordingRag()
    monkeypatch.setattr(chat_routes, "get_rag_client", lambda: rag)

    resp = client.post(
        "/api/chat",
        json={
            "question": "hello?",
            "storeIds": [store.id],
            "metadataFilter": {"tenant": "acme", "region": ["us-east1", "us-west1"]},
        },
    )

    assert resp.status_code == 200
    assert rag.seen_filter == {"tenant": "acme", "region": ["us-east1", "us-west1"]}
    assert "text-delta" in resp.content.decode()
