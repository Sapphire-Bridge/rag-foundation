from __future__ import annotations

import io
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import User, QueryLog, Budget
from app.costs import estimate_tokens_from_bytes, _resolve_model_rates
from app.config import settings


client = TestClient(app)


def _dev_token(email: str = "costs@example.com") -> str:
    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post("/api/auth/token", json={"email": email}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}


def _get_user(session: SessionLocal, email: str) -> User:
    return session.query(User).filter(User.email == email.lower()).one()


def test_costs_summary_includes_tokens_and_budget():
    email = "cost-summary@example.com"
    token = _dev_token(email)
    headers = _auth_headers(token)

    session = SessionLocal()
    try:
        user = _get_user(session, email)
        session.query(QueryLog).filter(QueryLog.user_id == user.id).delete()
        session.query(Budget).filter(Budget.user_id == user.id).delete()
        session.add(
            QueryLog(
                user_id=user.id,
                store_id=None,
                prompt_tokens=1000,
                completion_tokens=500,
                cost_usd=Decimal("0.0007"),
                model="gemini-2.5-flash",
            )
        )
        session.add(
            QueryLog(
                user_id=user.id,
                store_id=None,
                prompt_tokens=2000,
                completion_tokens=None,
                cost_usd=Decimal("0.00026"),
                model="INDEX",
            )
        )
        session.add(Budget(user_id=user.id, monthly_limit_usd=Decimal("50.00")))
        session.commit()
    finally:
        session.close()

    resp = client.get("/api/costs/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["prompt_tokens"] == 1000
    assert data["completion_tokens"] == 500
    assert data["index_tokens"] == 2000
    assert data["monthly_budget_usd"] == 50.0
    assert data["total_usd"] > 0


def test_upload_rejected_when_budget_would_be_exceeded():
    email = "cost-budget@example.com"
    token = _dev_token(email)
    headers = _auth_headers(token)

    store_resp = client.post("/api/stores", json={"display_name": "Cost Store"}, headers=headers)
    assert store_resp.status_code == 200, store_resp.text
    store_id = store_resp.json()["id"]

    session = SessionLocal()
    try:
        user = _get_user(session, email)
        session.query(Budget).filter(Budget.user_id == user.id).delete()
        session.add(Budget(user_id=user.id, monthly_limit_usd=Decimal("0.00005")))
        session.commit()
    finally:
        session.close()

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
    assert rates["index_price"] == settings.MODEL_PRICING["gemini-2.5-pro"]["index_price"]

    default_rates = _resolve_model_rates("unknown-model")
    assert default_rates["index_price"] == settings.MODEL_PRICING["default"]["index_price"]
