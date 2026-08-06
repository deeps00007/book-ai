import json
import math
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import BookChunk
from app.services.llm_gateway import llm_gateway, LLMResponse, Provider
from app.services.embedding_service import create_embedding
from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI Teacher assistant. Answer questions using ONLY the provided book excerpts.
If the answer is not found in the excerpts, say: "I couldn't find this information in the uploaded book."
Be concise, accurate, and educational. Cite the specific parts of the book you reference."""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0
    return dot / (norm_a * norm_b)


async def retrieve_relevant_chunks(
    db: AsyncSession,
    book_id: str,
    query: str,
    top_k: int = 5,
    chapter_id: str = None,
) -> list[dict]:
    query_embedding = await create_embedding(query)

    conditions = [
        BookChunk.book_id == book_id,
        BookChunk.embedding_json.isnot(None),
    ]
    if chapter_id:
        conditions.append(BookChunk.chapter_id == chapter_id)

    result = await db.execute(select(BookChunk).where(*conditions))
    chunks = result.scalars().all()

    scored = []
    for chunk in chunks:
        try:
            emb = json.loads(chunk.embedding_json)
            sim = cosine_similarity(query_embedding, emb)
            scored.append((sim, {
                "id": chunk.id,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "similarity": sim,
            }))
        except (json.JSONDecodeError, TypeError):
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def build_rag_prompt(query: str, chunks: list[dict], chat_history: list[dict] = None) -> list[dict]:
    context = "\n\n---\n\n".join(
        f"[Excerpt {i+1} (Relevance: {c['similarity']:.2f})]: {c['content']}"
        for i, c in enumerate(chunks)
    )

    user_message = f"""CONTEXT FROM THE BOOK:
{context}

PREVIOUS CONVERSATION:
{_format_history(chat_history) if chat_history else "None"}

QUESTION: {query}

Answer the question using only the context above."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def _format_history(history: list[dict]) -> str:
    if not history:
        return "None"
    formatted = []
    for msg in history[-6:]:
        formatted.append(f"{msg['role'].upper()}: {msg['content']}")
    return "\n".join(formatted)


async def ask_book(
    db: AsyncSession,
    book_id: str,
    question: str,
    chat_history: list[dict] = None,
    chapter_id: str = None,
) -> LLMResponse:
    chunks = await retrieve_relevant_chunks(db, book_id, question, chapter_id=chapter_id)
    messages = build_rag_prompt(question, chunks, chat_history)

    response = await llm_gateway.chat(
        messages=messages,
        provider=Provider.FIREWORKS,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )

    response.sources = chunks
    return response


async def ask_book_stream(
    db: AsyncSession,
    book_id: str,
    question: str,
    chat_history: list[dict] = None,
    chapter_id: str = None,
):
    chunks = await retrieve_relevant_chunks(db, book_id, question, chapter_id=chapter_id)
    messages = build_rag_prompt(question, chunks, chat_history)

    stream = llm_gateway.chat_stream(
        messages=messages,
        provider=Provider.FIREWORKS,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )

    async for chunk in stream:
        yield chunk

    yield {"sources": chunks, "__sources__": True}
