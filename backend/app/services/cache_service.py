"""
Answer cache — avoids re-calling the LLM (and spending tokens) when the same
or a near-identical question is asked again for the same book/chapter.
"""

import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AnswerCache

logger = logging.getLogger(__name__)


def normalize(question: str) -> str:
    """Lowercase, strip punctuation/extra whitespace for stable cache keys."""
    q = (question or "").lower().strip()
    q = re.sub(r"[^\w\s]", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q.strip()


async def get_cached(
    db: AsyncSession, book_id: str, question: str, chapter_id: str = None
):
    norm = normalize(question)
    if not norm:
        return None
    result = await db.execute(
        select(AnswerCache).where(
            AnswerCache.book_id == book_id,
            AnswerCache.question_norm == norm,
        ).limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    try:
        row.hits = (row.hits or 0) + 1
        await db.commit()
    except Exception:
        await db.rollback()
    logger.info(f"Cache HIT for book {book_id[:8]}")
    return {
        "answer": row.answer,
        "sources": (row.sources or {}).get("chunks", []) if row.sources else [],
        "provider": "cache",
        "model": "cache",
        "tokens_used": 0,
        "response_time_ms": 0,
    }


async def store_cached(
    db: AsyncSession, book_id: str, question: str, answer: str,
    sources: list = None, chapter_id: str = None,
):
    norm = normalize(question)
    if not norm or not answer:
        return
    try:
        existing = await db.execute(
            select(AnswerCache).where(
                AnswerCache.book_id == book_id,
                AnswerCache.question_norm == norm,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            return
        db.add(AnswerCache(
            book_id=book_id,
            chapter_id=chapter_id,
            question_norm=norm,
            question=question[:1000],
            answer=answer,
            sources={"chunks": sources} if sources else None,
        ))
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(f"Cache store failed: {e}")
