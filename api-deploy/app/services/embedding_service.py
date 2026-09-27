import logging
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.database import async_session
from app.services.api_key_pool import get_active_keys as get_pool_keys, mark_key_failed, mark_key_active, is_key_exhausted_error

logger = logging.getLogger(__name__)


async def _try_embedding(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def create_embedding(text: str, user_id: str = None, endpoint: str = "embedding:query") -> list[float]:
    embeddings = await create_embeddings_batch([text], user_id, endpoint=endpoint)
    return embeddings[0]


# Cache OpenAI clients by key so we don't rebuild them on every call.
_CLIENTS: dict[str, AsyncOpenAI] = {}


def _client_for(key: str) -> AsyncOpenAI:
    c = _CLIENTS.get(key)
    if c is None:
        # max_retries=0: fail fast on a 503 so the key pool can try another key
        # immediately instead of waiting ~5s on the SDK's backoff.
        c = AsyncOpenAI(api_key=key, base_url=(settings.fireworks_base_url or "").strip(), max_retries=0, timeout=15)
        _CLIENTS[key] = c
    return c


async def create_embeddings_batch(texts: list[str], user_id: str = None, endpoint: str = "embedding") -> list[list[float]]:
    pool_keys = []
    try:
        async with async_session() as db:
            pool_keys = await get_pool_keys(db, user_id)
    except Exception:
        pass

    keys_to_try = pool_keys if pool_keys else [{"id": None, "api_key": (settings.fireworks_api_key or "").strip(), "label": "default"}]

    last_error = None

    for entry in keys_to_try:
        key = (entry.get("api_key") or "").strip()
        kid = entry.get("id")

        try:
            client = _client_for(key)
            result = await _try_embedding(client, texts)

            if kid:
                await mark_key_active(kid)

            # log embedding usage (estimated tokens = chars / 4)
            if user_id:
                try:
                    from app.services import usage_service
                    async with async_session() as db:
                        await usage_service.log_usage(
                            db, user_id, "fireworks", settings.embedding_model, endpoint,
                            tokens_in=sum(len(t) // 4 for t in texts), tokens_out=0,
                        )
                except Exception:
                    pass

            return result

        except Exception as e:
            err_msg = str(e)[:200]
            logger.warning(f"Embedding key failed ({entry.get('label', 'unknown')}): {err_msg}")
            last_error = e

            if kid and is_key_exhausted_error(err_msg):
                await mark_key_failed(kid, err_msg)

    raise RuntimeError(f"All embedding keys exhausted. Last error: {last_error}")
