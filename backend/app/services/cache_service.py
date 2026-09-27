"""
Answer cache.

Two levels:
  1. Exact (normalised text) — free and instant.
  2. Semantic — if a very similar question was already answered
     (cosine similarity ≥ threshold), reuse it. Avoids LLM cost for
     paraphrases like "What is an ecosystem?" vs "define ecosystem".
"""

import re
import math
import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AnswerCache

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.93


def normalize(question: str) -> str:
    q = (question or "").lower().strip()
    q = re.sub(r"[^\w\s]", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q.strip()


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0


def _to_result(row: AnswerCache, provider: str = "cache") -> dict:
    return {
        "answer": row.answer,
        "sources": (row.sources or {}).get("chunks", []) if row.sources else [],
        "provider": provider,
        "model": provider,
        "tokens_used": 0,
        "response_time_ms": 0,
    }


async def get_cached(db: AsyncSession, book_id: str, question: str, chapter_id: str = None):
    """Exact (normalised) match."""
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
    logger.info(f"Cache HIT (exact) for book {book_id[:8]}")
    return _to_result(row, "cache")


async def get_cached_semantic(db: AsyncSession, book_id: str, question: str,
                              user_id: str = None, threshold: float = SIMILARITY_THRESHOLD,
                              query_embedding: list[float] = None):
    """Near-duplicate match via embedding similarity."""
    # Only pay for an embedding if this book actually has cached answers.
    try:
        n = await db.execute(
            select(AnswerCache.id).where(
                AnswerCache.book_id == book_id,
                AnswerCache.embedding_json.isnot(None),
            ).limit(1)
        )
        if n.first() is None:
            return None
    except Exception:
        return None

    q_emb = query_embedding
    if q_emb is None:
        try:
            from app.services.embedding_service import create_embedding
            q_emb = await create_embedding(question, user_id, endpoint="embedding:cache")
        except Exception:
            return None

    result = await db.execute(
        select(AnswerCache).where(
            AnswerCache.book_id == book_id,
            AnswerCache.embedding_json.isnot(None),
        )
    )
    rows = result.scalars().all()

    best = None
    best_sim = 0.0
    for row in rows:
        try:
            emb = json.loads(row.embedding_json)
            sim = _cos(q_emb, emb)
            if sim > best_sim:
                best_sim = sim
                best = row
        except Exception:
            continue

    if best and best_sim >= threshold:
        try:
            best.hits = (best.hits or 0) + 1
            await db.commit()
        except Exception:
            await db.rollback()
        logger.info(f"Cache HIT (semantic {best_sim:.3f}) for book {book_id[:8]}")
        return _to_result(best, "cache-semantic")
    return None


async def store_cached(db: AsyncSession, book_id: str, question: str, answer: str,
                       sources: list = None, chapter_id: str = None, user_id: str = None,
                       query_embedding: list[float] = None):
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

        emb_json = None
        if query_embedding is not None:
            emb_json = json.dumps(query_embedding)
        else:
            try:
                from app.services.embedding_service import create_embedding
                emb = await create_embedding(question, user_id, endpoint="embedding:store")
                emb_json = json.dumps(emb)
            except Exception:
                pass

        db.add(AnswerCache(
            book_id=book_id,
            chapter_id=chapter_id,
            question_norm=norm,
            question=question[:1000],
            answer=answer,
            sources={"chunks": sources} if sources else None,
            embedding_json=emb_json,
        ))
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(f"Cache store failed: {e}")
