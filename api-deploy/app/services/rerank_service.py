"""
Reranking with a dedicated cross-encoder reranker (Fireworks `/rerank`).

This is far faster (≈1s) and more accurate than asking a generative LLM to
score passages. Keys come from the platform key pool with failover.
"""

import logging
import httpx
from app.core.config import settings
from app.core.database import async_session
from app.services.api_key_pool import get_active_keys, is_key_exhausted_error, mark_key_failed

logger = logging.getLogger(__name__)

RERANK_MODEL = "accounts/fireworks/models/qwen3-reranker-8b"


async def _pool_keys(user_id: str = None) -> list[dict]:
    keys = []
    try:
        async with async_session() as db:
            keys = await get_active_keys(db, user_id)
    except Exception:
        pass
    if not keys:
        keys = [{"id": None, "api_key": (settings.fireworks_api_key or "").strip()}]
    return keys


async def rerank(question: str, candidates: list[dict], user_id: str = None,
                 top_k: int = 5, max_candidates: int = 12) -> list[dict]:
    """Return the top_k candidates reordered by relevance, best first."""
    if len(candidates) <= top_k:
        return candidates

    pool = candidates[:max_candidates]
    documents = [(c.get("content") or "").replace("\n", " ").strip()[:1500] for c in pool]

    for entry in await _pool_keys(user_id):
        key = (entry.get("api_key") or "").strip()
        if not key:
            continue
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                r = await client.post(
                    f"{settings.fireworks_base_url.rstrip('/')}/rerank",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": RERANK_MODEL, "query": question, "documents": documents,
                          "top_n": min(top_k, len(documents))},
                )
            if r.status_code != 200:
                msg = r.text[:150]
                logger.warning(f"Rerank failed ({r.status_code}): {msg}")
                if entry.get("id") and is_key_exhausted_error(msg):
                    await mark_key_failed(entry["id"], msg)
                continue

            data = r.json().get("data", [])
            ranked = []
            for item in data:
                idx = item.get("index")
                if isinstance(idx, int) and 0 <= idx < len(pool):
                    c = dict(pool[idx])
                    c["rerank_score"] = item.get("relevance_score", 0.0)
                    ranked.append(c)
            if ranked:
                # append a couple of unranked candidates as extra context
                chosen_ids = {c.get("id") for c in ranked}
                extras = [c for c in candidates if c.get("id") not in chosen_ids]
                return ranked[:top_k] + extras[:2]
        except Exception as e:
            logger.warning(f"Rerank error: {e}")
            continue

    # all keys failed → fall back to retrieval order
    return candidates[:top_k]
