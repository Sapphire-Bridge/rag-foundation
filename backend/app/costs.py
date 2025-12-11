import datetime
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .config import settings
from .models import Budget, QueryLog

MTOK = Decimal("1000000")
COST_PRECISION = Decimal("0.000001")


def _price_decimal(value: float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _quantize(value: Decimal) -> Decimal:
    quantized = value.quantize(COST_PRECISION, rounding=ROUND_HALF_UP)
    if value > 0 and quantized == 0:
        # Avoid losing tiny but non-zero costs to rounding.
        return COST_PRECISION
    return quantized


def _resolve_model_rates(model: str | None) -> dict[str, Decimal]:
    """
    Resolve per-model pricing with deterministic prefix fallback and explicit env overrides.
    """

    def _as_decimal(value: float | Decimal | None, fallback: float | Decimal) -> Decimal:
        try:
            if value is None:
                return _price_decimal(fallback)
            return _price_decimal(value)
        except Exception:
            return _price_decimal(fallback)

    def _fields_set() -> set[str]:
        fs = getattr(settings, "model_fields_set", None)
        if fs is None:
            fs = getattr(settings, "__fields_set__", None)
        return set(fs or ())

    def _explicit_override(env_key: str) -> bool:
        if env_key in _fields_set():
            return True
        if env_key in os.environ:
            return True
        if f"{env_key}_FILE" in os.environ:
            return True
        return False

    model_key = (model or "").strip()
    mp: dict[str, Any] = getattr(settings, "MODEL_PRICING", {}) or {}

    rates: dict[str, Any] = {}
    if model_key and model_key in mp:
        rates = mp.get(model_key) or {}
    elif model_key:
        best_key = None
        best_rates: dict[str, Any] = {}
        for k, v in mp.items():
            if k == "default":
                continue
            if model_key.startswith(k) and (best_key is None or len(k) > len(best_key)):
                best_key = k
                best_rates = v or {}
        rates = best_rates

    default_rates: dict[str, Any] = mp.get("default", {}) or {}

    price_fields: dict[str, tuple[str, float | Decimal]] = {
        "input_price": ("PRICE_PER_MTOK_INPUT", settings.PRICE_PER_MTOK_INPUT),
        "output_price": ("PRICE_PER_MTOK_OUTPUT", settings.PRICE_PER_MTOK_OUTPUT),
        "index_price": ("PRICE_PER_MTOK_INDEX", settings.PRICE_PER_MTOK_INDEX),
    }

    def _pick(rate_key: str) -> Decimal:
        setting_field, setting_value = price_fields[rate_key]

        if rate_key in rates and rates.get(rate_key) is not None:
            return _as_decimal(rates.get(rate_key), fallback=setting_value)

        if (
            rate_key in default_rates
            and default_rates.get(rate_key) is not None
            and not _explicit_override(setting_field)
        ):
            return _as_decimal(default_rates.get(rate_key), fallback=setting_value)

        return _as_decimal(
            getattr(settings, setting_field, setting_value),
            fallback=default_rates.get(rate_key, setting_value),
        )

    return {
        "input_price": _pick("input_price"),
        "output_price": _pick("output_price"),
        "index_price": _pick("index_price"),
    }


@dataclass
class QueryCostResult:
    model: str
    prompt_tokens: int
    completion_tokens: int
    prompt_cost_usd: Decimal
    completion_cost_usd: Decimal

    @property
    def total_cost_usd(self) -> Decimal:
        return _quantize(self.prompt_cost_usd + self.completion_cost_usd)


@dataclass
class IndexCostResult:
    tokens: int
    cost_usd: Decimal

    @property
    def total_cost_usd(self) -> Decimal:
        return self.cost_usd


def calc_query_cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> QueryCostResult:
    pt = max(prompt_tokens or 0, 0)
    ct = max(completion_tokens or 0, 0)
    rates = _resolve_model_rates(model)
    prompt_cost = _quantize((Decimal(pt) / MTOK) * _price_decimal(rates["input_price"]))
    completion_cost = _quantize((Decimal(ct) / MTOK) * _price_decimal(rates["output_price"]))
    return QueryCostResult(
        model=model,
        prompt_tokens=pt,
        completion_tokens=ct,
        prompt_cost_usd=prompt_cost,
        completion_cost_usd=completion_cost,
    )


def calc_index_cost(tokens: int | None, model: str | None = None) -> IndexCostResult:
    tok = max(tokens or 0, 0)
    rates = _resolve_model_rates(model or settings.DEFAULT_MODEL)
    idx_price = rates.get("index_price", settings.PRICE_PER_MTOK_INDEX)
    cost = _quantize((Decimal(tok) / MTOK) * _price_decimal(idx_price))
    return IndexCostResult(tokens=tok, cost_usd=cost)


def estimate_tokens_from_bytes(n_bytes: int, mime_type: str | None = None) -> int:
    """
    Estimate tokens with light modality awareness to avoid gross overestimation.
    Falls back to a text heuristic when the MIME type is unknown.
    """
    if n_bytes <= 0:
        return 0
    if mime_type:
        mt = mime_type.lower()
        if mt.startswith("image/"):
            return 1200  # most images tokenize under this ceiling
        if mt.startswith("audio/"):
            # Assume compressed speech; ~10k tokens per MB is a safe upper bound.
            return max(1000, int((n_bytes / (1024 * 1024)) * 10000))
    # coarse text estimate: ~4 bytes per token
    return max(0, n_bytes // 4)


def mtd_spend(db: Session, user_id: int) -> Decimal:
    now = datetime.datetime.now(datetime.timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = (
        db.query(func.coalesce(func.sum(QueryLog.cost_usd), 0))
        .filter(QueryLog.user_id == user_id, QueryLog.created_at >= month_start)
        .scalar()
    )
    return Decimal(total or 0)


def user_budget(db: Session, user_id: int) -> Decimal | None:
    b = db.query(Budget).filter(Budget.user_id == user_id).one_or_none()
    return Decimal(b.monthly_limit_usd) if b else None


def would_exceed_budget(db: Session, user_id: int, add_cost: Decimal) -> bool:
    limit = user_budget(db, user_id)
    if limit is None:
        return False
    return (mtd_spend(db, user_id) + add_cost) > limit


def acquire_budget_lock(db: Session, user_id: int) -> None:
    """
    Best-effort per-user lock to serialize budget checks.

    Uses FOR UPDATE on the budget row in Postgres; on other dialects falls back to a no-op
    select. Failures are swallowed to avoid breaking requests.
    """
    try:
        dialect = (db.bind.dialect.name if getattr(db, "bind", None) else "").lower()
    except Exception:
        dialect = ""

    stmt = None
    if dialect.startswith("postgres"):
        stmt = text("SELECT user_id FROM budgets WHERE user_id = :uid FOR UPDATE")
    elif dialect.startswith("sqlite"):
        stmt = text("SELECT user_id FROM budgets WHERE user_id = :uid")

    if stmt is not None:
        try:
            db.execute(stmt, {"uid": user_id})
        except Exception:
            pass


def pricing_configured() -> bool:
    try:
        rates = _resolve_model_rates(settings.DEFAULT_MODEL)
    except Exception:
        return False
    return rates.get("input_price", 0) > 0 and rates.get("output_price", 0) > 0 and rates.get("index_price", 0) > 0


def require_pricing_configured():
    if not pricing_configured():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pricing configuration missing; contact support",
        )
