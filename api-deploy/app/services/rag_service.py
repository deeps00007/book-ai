"""
Contextual RAG Pipeline - Optimized for speed and accuracy.
Single-pass chunk scoring, aggressive question anchoring.
"""

import json, math, re, logging
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import BookChunk
from app.services.llm_gateway import llm_gateway, LLMResponse, Provider
from app.services.embedding_service import create_embedding
from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI Teacher assistant that answers the user's question using ONLY the provided textbook excerpts.

SOURCE LOCK (highest priority — never break these):
- The provided textbook excerpts are the ONLY source of truth for the answer.
- Never use outside knowledge, general knowledge, or information from any other
  book, website, or subject — even if you already know it.
- Never add facts, examples, definitions, numbers, or details that are not
  present in the excerpts.
- If the excerpts do not contain the answer, reply with exactly one line:
  "This isn't covered in the provided book." — do not guess or fill in gaps.

ACCURACY RULES (follow these or the answer will be WRONG):

1. STORY TIMELINE: If the book is a narrative/story, events happen in ORDER.
   A question about an early event MUST be answered from early chapters/passages,
   NOT from similar-sounding passages that occur LATER in the story.
   Example: "What did Lencho hope for?" → He hoped for RAIN (early in story).
   Someone saying "he hoped for help from God" is a DIFFERENT event (after the hailstorm).
   Do NOT confuse them.

2. QUESTION IN TEXT: If the user's exact question appears in the provided context
   (marked with [QUESTION FOUND HERE]), answer from the paragraphs immediately
   surrounding that marker. IGNORE semantically similar sentences elsewhere.

3. LOCAL CONTEXT PRIORITY: The [LOCAL CONTEXT] excerpts (directly before/after the
   question) contain the answer. [OTHER CONTEXT] is background only and must not
   override the local context.

4. For comprehension questions: the answer follows the question in the textbook —
   look at the paragraphs AFTER the question, not before.

5. If the answer is genuinely not present in the excerpts, say so plainly in one line.

FORMATTING RULES (always follow — the answer is rendered as Markdown in a chat bubble):

- Write clean, well-structured Markdown. Make it easy to scan.
- Start with a one-line direct answer, then add supporting details.
- Keep paragraphs short (2–3 sentences). Avoid walls of text.
- Use a "## " heading ONLY if the answer has clearly distinct sections; otherwise skip headings.
- Use "- " bullet points for lists and "1." numbered lists for steps or sequences.
- Use **bold** for key terms and important values.
- Use a simple table only when comparing multiple items across the same attributes.
- Never mention the words "chunk", "chunk numbers", "[Chunk ...]", "context", or "excerpts".
  Do not cite chunk numbers or page numbers inline.
- Do not repeat the question back verbatim and do not add a closing summary like
  "In short, ..." unless it genuinely helps.
- Be concise and readable — prefer clarity over length."""


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _cos_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _bm25_score(ql: list[str], dl: list[str]) -> float:
    tf = {}
    for t in dl:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    doc_len = len(dl)
    avgdl = max(doc_len, 1)
    k1, b = 1.2, 0.75
    for qt in ql:
        f = tf.get(qt, 0)
        score += (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avgdl))
    return score


QUESTION_WORDS = {"what", "why", "how", "who", "when", "where", "which", "explain", "describe", "define", "list", "identify", "discuss"}


def _level_hint(book_title: str | None) -> str:
    """Detect the class/grade from the book title and return a tone hint."""
    if not book_title:
        return ""
    t = book_title.lower()
    m = re.search(r"(?:class|grade|std|standard)\s*(\d{1,2})", t)
    if not m:
        m = re.search(r"(\d{1,2})\s*(?:st|nd|rd|th)\b", t)
    if not m:
        m = re.search(r"\b(\d{1,2})\b\s*$", t)
    if m:
        grade = m.group(1)
        return (
            f"The reader is a Class {grade} student. Use simple, age-appropriate "
            f"language and short sentences suitable for that class level."
        )
    return ""


def _is_likely_question(text: str) -> bool:
    t = text.strip().lower()
    if t.endswith("?"):
        return True
    first = t.split()[0] if t.split() else ""
    return first in QUESTION_WORDS


async def retrieve_relevant_chunks(
    db: AsyncSession, book_id: str, query: str,
    top_k: int = 5, chapter_id: str = None, user_id: str = None,
    query_embedding: list[float] = None,
) -> list[dict]:
    import time as _t
    _t0 = _t.time()
    if query_embedding is None:
        query_embedding = await create_embedding(query, user_id)
    _t1 = _t.time()
    query_lower = query.lower().rstrip("?").strip()
    is_question = _is_likely_question(query)
    qtokens = _tokenize(query)

    # Load all chunks once
    conds = [BookChunk.book_id == book_id, BookChunk.embedding_json.isnot(None)]
    if chapter_id:
        conds.append(BookChunk.chapter_id == chapter_id)
    result = await db.execute(select(BookChunk).where(*conds))
    all_chunks = result.scalars().all()
    logger.info(f"[rag] embed={(_t1-_t0)*1000:.0f}ms load={(_t.time()-_t1)*1000:.0f}ms chunks={len(all_chunks)}")

    # Phase 1: Fast vector scoring + question anchoring on all chunks
    vector_scored = []
    question_anchor_idx = None
    all_anchor_chunks = []

    for c in all_chunks:
        try:
            emb = json.loads(c.embedding_json)
            vec = _cos_sim(query_embedding, emb)
        except Exception:
            vec = 0

        is_anchor = False
        if is_question and query_lower and len(query_lower) > 5:
            cl = c.content.lower()
            if query_lower in cl:
                is_anchor = True
            else:
                for sent in cl.replace("?", " .").replace("!", " .").split("."):
                    s_stripped = sent.strip()
                    if s_stripped and _similarity(query_lower, s_stripped) > 0.8:
                        is_anchor = True
                        break

        entry = {
            "chunk": c, "vector_score": vec, "is_anchor": is_anchor,
            "chunk_index": c.chunk_index, "id": c.id,
        }
        vector_scored.append(entry)

        if is_anchor:
            all_anchor_chunks.append(entry)
            if question_anchor_idx is None:
                question_anchor_idx = c.chunk_index

    # Phase 2: Take top 50 by vector score for expensive BM25 scoring
    vector_scored.sort(key=lambda x: x["vector_score"], reverse=True)
    top_candidates = vector_scored[:50]

    # Also include anchor neighbors (up to ±3 from each anchor)
    if question_anchor_idx is not None:
        for entry in vector_scored:
            if abs(entry["chunk_index"] - question_anchor_idx) <= 3:
                if entry not in top_candidates:
                    top_candidates.append(entry)

    # Phase 3: Full scoring (BM25 + hybrid) only on top candidates
    scored = []
    for entry in top_candidates:
        c = entry["chunk"]
        vec = entry["vector_score"]
        is_anchor = entry["is_anchor"]
        bm25 = _bm25_score(qtokens, _tokenize(c.content))
        hybrid = vec * 0.4 + bm25 * 0.6

        if is_anchor:
            hybrid = max(hybrid, 0.95)

        scored.append({
            "id": c.id, "content": c.content,
            "chunk_index": c.chunk_index,
            "page_start": c.page_start or 0,
            "page_end": c.page_end or 0,
            "chapter_id": c.chapter_id,
            "score": hybrid, "vector_score": vec,
            "bm25_score": bm25, "is_anchor": is_anchor,
        })

    # Proximity boost
    if question_anchor_idx is not None:
        for s in scored:
            dist = abs(s["chunk_index"] - question_anchor_idx)
            if dist <= 3:
                s["score"] += (4 - dist) * 0.12

    scored.sort(key=lambda c: c["score"], reverse=True)

    # Build a generous candidate pool (question-anchor neighbours first).
    if question_anchor_idx is not None:
        neighbors = [s for s in scored if abs(s["chunk_index"] - question_anchor_idx) <= 2]
        others = [s for s in scored if abs(s["chunk_index"] - question_anchor_idx) > 2]
        seen = set()
        pool = []
        for s in neighbors + others:
            if s["id"] not in seen:
                seen.add(s["id"])
                pool.append(s)
    else:
        pool = scored

    pool = pool[:12]

    # If we found the exact question in the book, the local context is already
    # reliable — skip the (slow) LLM rerank. Only rerank ambiguous retrievals.
    if question_anchor_idx is not None:
        return pool[:top_k]

    from app.services import rerank_service
    _tr = _t.time()
    out = await rerank_service.rerank(query, pool, user_id=user_id, top_k=top_k)
    logger.info(f"[rag] rerank={(_t.time()-_tr)*1000:.0f}ms")
    return out


def build_rag_prompt(query: str, chunks: list[dict], chat_history: list[dict] = None,
                     book_title: str = None) -> list[dict]:
    anchor_idx = None
    for i, c in enumerate(chunks):
        if c.get("is_anchor") and anchor_idx is None:
            anchor_idx = c.get("chunk_index")
            break

    local_parts = []
    other_parts = []
    for i, c in enumerate(chunks):
        ci = c.get("chunk_index", 0)
        in_local = anchor_idx is not None and abs(ci - anchor_idx) <= 2

        lbl = "[Excerpt"
        if c.get("page_start"):
            lbl += f", p.{c['page_start']}"
        lbl += "]"

        if c.get("is_anchor"):
            lbl += " ← QUESTION FOUND HERE"
        elif in_local:
            lbl += " ← LOCAL CONTEXT (near question)"
        elif anchor_idx is not None:
            lbl += " ← OTHER CONTEXT (further away)"

        body = (c.get("content") or "")[:1800]
        if in_local:
            local_parts.append(f"{lbl}: {body}")
        else:
            other_parts.append(f"{lbl}: {body}")

    context = ""
    if local_parts:
        context += "=== LOCAL CONTEXT (must use these for answer) ===\n\n"
        context += "\n\n---\n\n".join(local_parts)
    if other_parts:
        if local_parts:
            context += "\n\n=== OTHER CONTEXT (background only) ===\n\n"
        context += "\n\n---\n\n".join(other_parts)

    instr = ""
    if anchor_idx is not None:
        instr = (
            "\n\nCRITICAL: The [QUESTION FOUND HERE] excerpt contains the user's exact question "
            "from the textbook. The answer MUST come from the [LOCAL CONTEXT] excerpts "
            "immediately before and after that question. "
            "[OTHER CONTEXT] excerpts may be from a different part of the book — "
            "their similar words do NOT make them the answer. "
            "Consider the STORY TIMELINE — events happen in order."
        )

    book_line = f"\n\nBOOK: \"{book_title}\"" if book_title else ""
    level = _level_hint(book_title)
    level_line = f"\nAUDIENCE: {level}" if level else ""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{context}{instr}{book_line}{level_line}\n\nPREVIOUS:\n{_fmt(chat_history)}\n\nQUESTION: {query}"},
    ]


def _fmt(h: list[dict]) -> str:
    if not h:
        return "None"
    return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in h[-6:])


async def ask_book(
    db: AsyncSession, book_id: str, question: str,
    chat_history: list[dict] = None, chapter_id: str = None,
    user_id: str = None, query_embedding: list[float] = None,
    book_title: str = None,
) -> LLMResponse:
    chunks = await retrieve_relevant_chunks(
        db, book_id, question, top_k=5, chapter_id=chapter_id, user_id=user_id,
        query_embedding=query_embedding,
    )
    messages = build_rag_prompt(question, chunks, chat_history, book_title=book_title)
    response = await llm_gateway.chat(
        messages=messages, provider=Provider.FIREWORKS,
        temperature=settings.temperature, max_tokens=settings.max_tokens,
        user_id=user_id,
    )
    response.sources = chunks
    return response


async def ask_book_stream(
    db: AsyncSession, book_id: str, question: str,
    chat_history: list[dict] = None, chapter_id: str = None,
    user_id: str = None, query_embedding: list[float] = None,
    book_title: str = None,
):
    chunks = await retrieve_relevant_chunks(
        db, book_id, question, top_k=5, chapter_id=chapter_id, user_id=user_id,
        query_embedding=query_embedding,
    )
    messages = build_rag_prompt(question, chunks, chat_history, book_title=book_title)
    stream = llm_gateway.chat_stream(
        messages=messages, provider=Provider.FIREWORKS,
        temperature=settings.temperature, max_tokens=settings.max_tokens,
        user_id=user_id,
    )
    async for chunk in stream:
        yield chunk
    yield {"sources": chunks, "__sources__": True}
