import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import engine

logger = logging.getLogger(__name__)


def is_key_exhausted_error(err_msg: str) -> bool:
    """Only these errors mean the KEY/account is dead. Transient/model errors should not exhaust a key."""
    e = err_msg.lower()
    markers = [
        "412", "suspended", "401", "unauthorized", "403", "forbidden",
        "invalid api key", "spending limit", "quota", "billing",
        "account", "credit",
    ]
    return any(m in e for m in markers)


async def get_active_keys(db: AsyncSession, user_id: str = None) -> list[dict]:
    """Platform-wide key pool — shared across ALL users.

    The user_id argument is accepted for backwards compatibility but the
    keys are global: they are the platform's keys, not each user's.
    """
    result = await db.execute(
        text("SELECT id, label, api_key, status, error_count, last_error FROM api_keys WHERE status = 'active' ORDER BY error_count ASC, created_at ASC"),
    )
    return [dict(row._mapping) for row in result]


async def mark_key_failed(key_id: str, error_msg: str):
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("UPDATE api_keys SET status = 'exhausted', last_error = :err, error_count = error_count + 1 WHERE id = :kid"),
                {"err": error_msg[:500], "kid": key_id},
            )
            await conn.commit()
        logger.info(f"Key {key_id[:8]} marked exhausted")
    except Exception as e:
        logger.error(f"Failed to mark key {key_id[:8]} exhausted: {e}")


async def mark_key_active(key_id: str):
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("UPDATE api_keys SET last_used = :now WHERE id = :kid"),
                {"now": datetime.now(timezone.utc), "kid": key_id},
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark key {key_id[:8]} active: {e}")


async def add_api_key(db: AsyncSession, user_id: str, api_key: str, label: str = "", provider: str = "fireworks") -> dict:
    result = await db.execute(
        text(
            "INSERT INTO api_keys (user_id, label, api_key, provider, status) "
            "VALUES (:uid, :label, :key, :provider, 'active') RETURNING id"
        ),
        {"uid": user_id, "label": label, "key": api_key, "provider": provider},
    )
    await db.commit()
    row = result.fetchone()
    return {"id": row[0], "status": "active"}


async def list_api_keys(db: AsyncSession, user_id: str) -> list[dict]:
    result = await db.execute(
        text("SELECT id, label, provider, status, error_count, last_error, last_used, created_at FROM api_keys WHERE user_id = :uid ORDER BY created_at DESC"),
        {"uid": user_id},
    )
    rows = result.fetchall()
    return [
        {
            "id": r[0], "label": r[1], "provider": r[2], "status": r[3],
            "error_count": r[4], "last_error": r[5],
            "last_used": str(r[6]) if r[6] else None,
            "created_at": str(r[7]) if r[7] else None,
        }
        for r in rows
    ]


async def delete_api_key(db: AsyncSession, key_id: str, user_id: str):
    await db.execute(
        text("DELETE FROM api_keys WHERE id = :kid AND user_id = :uid"),
        {"kid": key_id, "uid": user_id},
    )
    await db.commit()
