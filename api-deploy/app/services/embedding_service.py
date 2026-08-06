import logging
from openai import AsyncOpenAI
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.fireworks_api_key,
            base_url=settings.fireworks_base_url,
        )
    return _client


async def create_embedding(text: str) -> list[float]:
    response = await _get_client().embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return response.data[0].embedding


async def create_embeddings_batch(texts: list[str]) -> list[list[float]]:
    response = await _get_client().embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]
