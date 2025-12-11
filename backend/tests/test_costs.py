from __future__ import annotations

import io
from decimal import Decimal
from types import SimpleNamespace

import app.costs as costs
from app.models import User, QueryLog, Budget
from app.costs import estimate_tokens_from_bytes, _resolve_model_rates
from app.config import settings


def _dev_token(client, email: str = "costs@example.com") -> str:
    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post("/api/auth/token", json={"email": email}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def _get_user(session, email: str) -> User:
    return session.query(User).filter(User.email == email.lower()).one()


def test_costs_summary_includes_tokens_and_budget(client, db_session):
    email = "cost-summary@example.com"
    token = _dev_token(client, email)
    headers = _auth_headers(token)

    user = _get_user(db_session, email)
    db_session.query(QueryLog).filter(QueryLog.user_id == user.id).delete()
    db_session.query(Budget).filter(Budget.user_id == user.id).delete()
    db_session.add(
        QueryLog(
            user_id=user.id,
            store_id=None,
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=Decimal("0.0007"),
            model="gemini-2.5-flash",
        )
    )
    db_session.add(
        QueryLog(
            user_id=user.id,
            store_id=None,
            prompt_tokens=2000,
            completion_tokens=None,
            cost_usd=Decimal("0.00026"),
            model="INDEX",
        )
    )
    db_session.add(Budget(user_id=user.id, monthly_limit_usd=Decimal("50.00")))
    db_session.commit()

    resp = client.get("/api/costs/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["prompt_tokens"] == 1000
    assert data["completion_tokens"] == 500
    assert data["index_tokens"] == 2000
    assert data["monthly_budget_usd"] == 50.0
    assert data["total_usd"] > 0


def test_upload_rejected_when_budget_would_be_exceeded(client, db_session):
    email = "cost-budget@example.com"
    token = _dev_token(client, email)
    headers = _auth_headers(token)

    store_resp = client.post("/api/stores", json={"display_name": "Cost Store"}, headers=headers)
    assert store_resp.status_code == 200, store_resp.text
    store_id = store_resp.json()["id"]

    user = _get_user(db_session, email)
    db_session.query(Budget).filter(Budget.user_id == user.id).delete()
    db_session.add(Budget(user_id=user.id, monthly_limit_usd=Decimal("0.00005")))
    db_session.commit()

    file_bytes = b"%PDF-1.4\n" + b"x" * 8000 + b"\n%%EOF"
    files = {"file": ("budget.pdf", io.BytesIO(file_bytes), "application/pdf")}
    data = {"storeId": str(store_id)}
    resp = client.post("/api/upload", data=data, files=files, headers=headers)
    assert resp.status_code == 402, resp.text


def test_estimate_tokens_handles_modalities():
    assert estimate_tokens_from_bytes(0) == 0
    assert estimate_tokens_from_bytes(100, "image/png") == 1200
    assert estimate_tokens_from_bytes(1024, "audio/wav") >= 1000


def test_resolve_model_rates_prefix_and_default():
    rates = _resolve_model_rates("gemini-2.5-pro-custom")
    expected_prefix = Decimal(str(settings.MODEL_PRICING["gemini-2.5-pro"]["index_price"]))
    assert rates["index_price"] == expected_prefix

    default_rates = _resolve_model_rates("unknown-model")
    expected_default = Decimal(str(settings.MODEL_PRICING["default"]["index_price"]))
    assert default_rates["index_price"] == expected_default


def test_resolve_model_rates_env_override_overrides_model_default(monkeypatch):
    dummy_settings = SimpleNamespace(
        MODEL_PRICING={"default": {"input_price": 0.30, "output_price": 2.50, "index_price": 0.0015}},
        PRICE_PER_MTOK_INPUT=Decimal("0.42"),
        PRICE_PER_MTOK_OUTPUT=Decimal("2.50"),
        PRICE_PER_MTOK_INDEX=Decimal("0.0015"),
        model_fields_set=set(),
    )
    monkeypatch.setattr(costs, "settings", dummy_settings, raising=False)
    monkeypatch.setenv("PRICE_PER_MTOK_INPUT", "0.42")

    rates = costs._resolve_model_rates("gemini-1.5-pro")
    assert rates["input_price"] == Decimal("0.42")
    assert rates["output_price"] == Decimal("2.50")
    assert rates["index_price"] == Decimal("0.0015")


def test_resolve_model_rates_model_specific_beats_env_override(monkeypatch):
    dummy_settings = SimpleNamespace(
        MODEL_PRICING={
            "default": {"input_price": 0.30, "output_price": 2.50, "index_price": 0.0015},
            "gemini-1.5-pro": {"input_price": 0.10, "output_price": 0.20, "index_price": 0.30},
        },
        PRICE_PER_MTOK_INPUT=Decimal("9.99"),
        PRICE_PER_MTOK_OUTPUT=Decimal("9.99"),
        PRICE_PER_MTOK_INDEX=Decimal("9.99"),
        model_fields_set=set(),
    )
    monkeypatch.setattr(costs, "settings", dummy_settings, raising=False)
    monkeypatch.setenv("PRICE_PER_MTOK_INPUT", "9.99")
    monkeypatch.setenv("PRICE_PER_MTOK_OUTPUT", "9.99")
    monkeypatch.setenv("PRICE_PER_MTOK_INDEX", "9.99")

    rates = costs._resolve_model_rates("gemini-1.5-pro")
    assert rates["input_price"] == Decimal("0.10")
    assert rates["output_price"] == Decimal("0.20")
    assert rates["index_price"] == Decimal("0.30")


def test_resolve_model_rates_longest_prefix_match(monkeypatch):
    dummy_settings = SimpleNamespace(
        MODEL_PRICING={
            "default": {"input_price": 0.30, "output_price": 2.50, "index_price": 0.0015},
            "gemini-1.5-": {"input_price": 0.11},
            "gemini-1.5-pro": {"input_price": 0.22},
        },
        PRICE_PER_MTOK_INPUT=Decimal("0.30"),
        PRICE_PER_MTOK_OUTPUT=Decimal("2.50"),
        PRICE_PER_MTOK_INDEX=Decimal("0.0015"),
        model_fields_set=set(),
    )
    monkeypatch.setattr(costs, "settings", dummy_settings, raising=False)

    rates = costs._resolve_model_rates("gemini-1.5-pro-002")
    assert rates["input_price"] == Decimal("0.22")


def test_resolve_model_rates_file_env_presence_counts_as_override(monkeypatch):
    dummy_settings = SimpleNamespace(
        MODEL_PRICING={"default": {"input_price": 0.30, "output_price": 2.50, "index_price": 0.0015}},
        PRICE_PER_MTOK_INPUT=Decimal("0.42"),
        PRICE_PER_MTOK_OUTPUT=Decimal("2.50"),
        PRICE_PER_MTOK_INDEX=Decimal("0.0015"),
        model_fields_set=set(),
    )
    monkeypatch.setattr(costs, "settings", dummy_settings, raising=False)
    monkeypatch.setenv("PRICE_PER_MTOK_INPUT_FILE", "/run/secrets/price_per_mtok_input")

    rates = costs._resolve_model_rates("gemini-1.5-pro")
    assert rates["input_price"] == Decimal("0.42")
