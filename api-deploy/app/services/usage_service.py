"""
Usage & cost tracking.

Prices are USD per 1,000,000 tokens (adjust to your current provider rates).
Every AI call should call `log_usage`; the dashboard reads `get_summary`.
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import APIUsageLog

logger = logging.getLogger(__name__)

# USD per 1M tokens: (input, output)
PRICES = {
    "deepseek-v4p1-flash": (0.15, 0.60),
    "deepseek-v4-flash": (0.15, 0.60),
    "deepseek-v4-pro": (0.90, 0.90),
    "glm-5p2": (0.20, 0.60),
    "glm-5p3": (0.20, 0.60),
    "kimi-k3": (0.60, 2.50),
    "minimax-m3": (0.30, 1.20),
    "nomic-ai/nomic-embed-text-v1.5": (0.02, 0.0),
}
DEFAULT_PRICE = (0.20, 0.80)


def _price_for(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for key, price in PRICES.items():
        if key.lower() in m:
            return price
    return DEFAULT_PRICE


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = _price_for(model)
    return (tokens_in / 1_000_000) * pin + (tokens_out / 1_000_000) * pout


async def log_usage(
    db: AsyncSession, user_id: str, provider: str, model: str, endpoint: str,
    tokens_in: int = 0, tokens_out: int = 0, response_time_ms: int = 0,
    success: bool = True, cached: bool = False, book_id: str = None,
    error_message: str = None,
):
    cost = 0.0 if cached else estimate_cost(model, tokens_in, tokens_out)
    try:
        db.add(APIUsageLog(
            user_id=user_id, provider=provider, model=model, endpoint=endpoint,
            book_id=book_id, tokens_in=tokens_in, tokens_out=tokens_out,
            cost_estimate=cost, response_time_ms=response_time_ms,
            success=success, cached=cached, error_message=error_message,
        ))
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(f"usage log failed: {e}")


async def _sum(db, stmt):
    r = await db.execute(stmt)
    return r.scalar() or 0


async def get_summary(db: AsyncSession, user_id: str, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    base = [APIUsageLog.user_id == user_id, APIUsageLog.created_at >= since]

    total = await _sum(db, select(func.count()).select_from(APIUsageLog).where(*base))
    cached_count = await _sum(db, select(func.count()).select_from(APIUsageLog).where(*base, APIUsageLog.cached.is_(True)))
    tok_in = await _sum(db, select(func.coalesce(func.sum(APIUsageLog.tokens_in), 0)).where(*base))
    tok_out = await _sum(db, select(func.coalesce(func.sum(APIUsageLog.tokens_out), 0)).where(*base))
    cost = await _sum(db, select(func.coalesce(func.sum(APIUsageLog.cost_estimate), 0)).where(*base))
    avg_ms = await _sum(db, select(func.coalesce(func.avg(APIUsageLog.response_time_ms), 0)).where(*base))

    # what the cached answers *would* have cost (rough average of a fresh call)
    fresh = max(total - cached_count, 1)
    avg_cost = (cost / fresh) if cost else 0.0
    saved = round(avg_cost * cached_count, 6)

    return {
        "days": days,
        "total_requests": total,
        "cached_requests": cached_count,
        "cache_hit_rate": round((cached_count / total * 100), 1) if total else 0.0,
        "tokens_in": tok_in,
        "tokens_out": tok_out,
        "total_tokens": tok_in + tok_out,
        "estimated_cost_usd": round(float(cost), 6),
        "estimated_cost_inr": round(float(cost) * 83, 4),
        "estimated_savings_usd": saved,
        "avg_response_ms": int(avg_ms or 0),
    }


async def get_daily(db: AsyncSession, user_id: str, days: int = 14) -> list[dict]:
    since = datetime.utcnow() - timedelta(days=days)
    day = func.date(APIUsageLog.created_at)
    r = await db.execute(
        select(
            day.label("d"),
            func.count().label("requests"),
            func.coalesce(func.sum(APIUsageLog.cost_estimate), 0).label("cost"),
            func.coalesce(func.sum(APIUsageLog.tokens_in + APIUsageLog.tokens_out), 0).label("tokens"),
        )
        .where(APIUsageLog.user_id == user_id, APIUsageLog.created_at >= since)
        .group_by(day)
        .order_by(day)
    )
    return [
        {"date": str(row.d), "requests": row.requests, "cost": round(float(row.cost), 6), "tokens": row.tokens}
        for row in r.fetchall()
    ]


async def get_by_model(db: AsyncSession, user_id: str, days: int = 30) -> list[dict]:
    since = datetime.utcnow() - timedelta(days=days)
    r = await db.execute(
        select(
            APIUsageLog.model,
            func.count().label("requests"),
            func.coalesce(func.sum(APIUsageLog.tokens_in + APIUsageLog.tokens_out), 0).label("tokens"),
            func.coalesce(func.sum(APIUsageLog.cost_estimate), 0).label("cost"),
        )
        .where(APIUsageLog.user_id == user_id, APIUsageLog.created_at >= since)
        .group_by(APIUsageLog.model)
        .order_by(func.coalesce(func.sum(APIUsageLog.cost_estimate), 0).desc())
    )
    return [
        {"model": row.model, "requests": row.requests, "tokens": row.tokens, "cost": round(float(row.cost), 6)}
        for row in r.fetchall()
    ]
