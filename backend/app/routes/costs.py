import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from ..db import get_db
from ..auth import get_current_user
from ..schemas import CostsSummary
from ..models import QueryLog, User
from ..costs import user_budget, mtd_spend, require_pricing_configured

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/summary", response_model=CostsSummary)
def costs_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_pricing_configured),
) -> CostsSummary:
    now = datetime.datetime.now(datetime.timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    query_row = (
        db.query(
            func.coalesce(func.sum(QueryLog.cost_usd), 0),
            func.coalesce(func.sum(QueryLog.prompt_tokens), 0),
            func.coalesce(func.sum(QueryLog.completion_tokens), 0),
        )
        .filter(
            QueryLog.user_id == user.id,
            QueryLog.created_at >= month_start,
            or_(QueryLog.model != "INDEX", QueryLog.model.is_(None)),
        )
        .one()
    )
    index_row = (
        db.query(
            func.coalesce(func.sum(QueryLog.cost_usd), 0),
            func.coalesce(func.sum(QueryLog.prompt_tokens), 0),
        )
        .filter(
            QueryLog.user_id == user.id,
            QueryLog.created_at >= month_start,
            QueryLog.model == "INDEX",
        )
        .one()
    )

    query_cost = float(query_row[0] or 0)
    indexing_cost = float(index_row[0] or 0)
    total = round(query_cost + indexing_cost, 6)

    budget = user_budget(db, user.id)
    spend = mtd_spend(db, user.id)
    remaining = None
    if budget is not None:
        remaining = float(max(budget - spend, Decimal("0")))

    return CostsSummary(
        month=month_start.strftime("%Y-%m"),
        query_cost_usd=round(query_cost, 6),
        indexing_cost_usd=round(indexing_cost, 6),
        total_usd=total,
        prompt_tokens=int(query_row[1] or 0),
        completion_tokens=int(query_row[2] or 0),
        index_tokens=int(index_row[1] or 0),
        monthly_budget_usd=float(budget) if budget is not None else None,
        remaining_budget_usd=remaining,
    )
