import time
import logging
from enum import Enum
from typing import AsyncIterator
from dataclasses import dataclass, field
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.core.database import async_session
from app.services.api_key_pool import get_active_keys, mark_key_failed, mark_key_active, is_key_exhausted_error

settings = get_settings()
logger = logging.getLogger(__name__)


class Provider(str, Enum):
    FIREWORKS = "fireworks"
    OPENAI = "openai"
    GEMINI = "gemini"
    GROQ = "groq"
    ANTHROPIC = "anthropic"


PROVIDER_CONFIG = {
    Provider.FIREWORKS: {
        "api_key": (settings.fireworks_api_key or "").strip(),
        "base_url": (settings.fireworks_base_url or "").strip(),
        "default_model": "accounts/fireworks/models/deepseek-v4p1-flash",
    },
    Provider.OPENAI: {
        "api_key": (settings.openai_api_key or "").strip(),
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    Provider.GROQ: {
        "api_key": (settings.groq_api_key or "").strip(),
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
}


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    tokens_used: int
    response_time_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    sources: list[dict] = field(default_factory=list)


class LLMGateway:
    def __init__(self):
        self.clients: dict[str, AsyncOpenAI] = {}
        self._init_clients()
        self._provider_order: list[Provider] = [
            Provider.FIREWORKS,
            Provider.GROQ,
            Provider.OPENAI,
        ]
        self._current_index = 0
        self._provider_health: dict[str, bool] = {
            p.value: True for p in self._provider_order
        }
        self._cooldown_until: dict[str, float] = {}

    def _init_clients(self):
        for provider, config in PROVIDER_CONFIG.items():
            if config["api_key"]:
                self.clients[provider.value] = AsyncOpenAI(
                    api_key=config["api_key"],
                    base_url=config["base_url"],
                )

    def _get_next_provider(self) -> Provider | None:
        for i in range(len(self._provider_order)):
            idx = (self._current_index + i) % len(self._provider_order)
            provider = self._provider_order[idx]
            key = provider.value

            if key not in self.clients:
                continue
            if not self._provider_health.get(key, True):
                continue
            if key in self._cooldown_until and time.time() < self._cooldown_until[key]:
                continue

            self._current_index = (idx + 1) % len(self._provider_order)
            return provider
        return None

    def _mark_failed(self, provider: str):
        self._provider_health[provider] = False
        self._cooldown_until[provider] = time.time() + 30
        logger.warning(f"Provider {provider} marked as unhealthy for 30s")

    def _mark_healthy(self, provider: str):
        self._provider_health[provider] = True
        self._cooldown_until.pop(provider, None)

    async def chat(
        self,
        messages: list[dict],
        provider: Provider | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        user_id: str = None,
    ) -> LLMResponse:
        start_time = time.time()
        temp = temperature if temperature is not None else settings.temperature
        max_tok = max_tokens if max_tokens is not None else settings.max_tokens

        pool_keys = []
        if not provider or provider == Provider.FIREWORKS:
            try:
                async with async_session() as db:
                    pool_keys = await get_active_keys(db, user_id)
            except Exception:
                pass

        for entry in pool_keys:
            key = entry["api_key"]
            kid = entry.get("id")
            try:
                client = AsyncOpenAI(api_key=key, base_url=(settings.fireworks_base_url or "").strip())
                actual_model = model or PROVIDER_CONFIG[Provider.FIREWORKS]["default_model"]
                response = await client.chat.completions.create(
                    model=actual_model, messages=messages, temperature=temp, max_tokens=max_tok,
                )
                if kid:
                    try:
                        await mark_key_active(kid)
                    except Exception:
                        pass
                elapsed = int((time.time() - start_time) * 1000)
                return LLMResponse(
                    content=response.choices[0].message.content,
                    provider=Provider.FIREWORKS.value,
                    model=actual_model,
                    tokens_used=response.usage.total_tokens if response.usage else 0,
                    response_time_ms=elapsed,
                    tokens_in=(getattr(response.usage, "prompt_tokens", 0) if response.usage else 0),
                    tokens_out=(getattr(response.usage, "completion_tokens", 0) if response.usage else 0),
                )
            except Exception as e:
                err_msg = str(e)[:200]
                logger.warning(f"LLM key failed ({entry.get('label','unknown')}): {err_msg}")
                if kid:
                    try:
                        if is_key_exhausted_error(err_msg): await mark_key_failed(kid, err_msg)
                    except Exception:
                        pass

        if provider and provider.value in self.clients:
            providers_to_try = [provider]
        else:
            providers_to_try = self._provider_order

        last_error = None
        for attempt in range(3):
            prov = (
                providers_to_try[0]
                if provider and provider.value in self.clients
                else self._get_next_provider()
            )
            if prov is None:
                raise Exception("No healthy LLM providers available")

            config = PROVIDER_CONFIG[prov]
            client = self.clients.get(prov.value)
            if not client:
                continue

            actual_model = model or config["default_model"]
            try:
                response = await client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tok,
                )
                self._mark_healthy(prov.value)
                elapsed = int((time.time() - start_time) * 1000)
                return LLMResponse(
                    content=response.choices[0].message.content,
                    provider=prov.value,
                    model=actual_model,
                    tokens_used=response.usage.total_tokens if response.usage else 0,
                    response_time_ms=elapsed,
                    tokens_in=(getattr(response.usage, "prompt_tokens", 0) if response.usage else 0),
                    tokens_out=(getattr(response.usage, "completion_tokens", 0) if response.usage else 0),
                )
            except Exception as e:
                last_error = e
                self._mark_failed(prov.value)
                logger.error(f"Provider {prov.value} failed: {e}")

        raise Exception(f"All providers failed. Last error: {last_error}")

    async def chat_stream(
        self,
        messages: list[dict],
        provider: Provider | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        user_id: str = None,
    ) -> AsyncIterator[dict]:
        temp = temperature if temperature is not None else settings.temperature
        max_tok = max_tokens if max_tokens is not None else settings.max_tokens

        if not provider or provider == Provider.FIREWORKS:
            try:
                async with async_session() as db:
                    pool_keys = await get_active_keys(db, user_id)
                for entry in pool_keys:
                    try:
                        client = AsyncOpenAI(api_key=entry["api_key"], base_url=(settings.fireworks_base_url or "").strip())
                        actual_model = model or PROVIDER_CONFIG[Provider.FIREWORKS]["default_model"]
                        stream = await client.chat.completions.create(
                            model=actual_model, messages=messages, temperature=temp, max_tokens=max_tok, stream=True,
                            stream_options={"include_usage": True})
                        _usage = None
                        async for chunk in stream:
                            if getattr(chunk, "usage", None):
                                _usage = chunk.usage
                            delta = chunk.choices[0].delta if chunk.choices else None
                            if delta and delta.content:
                                yield {"content": delta.content, "provider": Provider.FIREWORKS.value, "model": actual_model}
                        if _usage:
                            yield {"__usage__": {
                                "provider": Provider.FIREWORKS.value, "model": actual_model,
                                "tokens_in": getattr(_usage, "prompt_tokens", 0) or 0,
                                "tokens_out": getattr(_usage, "completion_tokens", 0) or 0,
                            }}
                        if entry.get("id"):
                            try:
                                await mark_key_active(entry["id"])
                            except Exception:
                                pass
                        return
                    except Exception as e:
                        logger.warning(f"Stream key failed: {str(e)[:100]}")
                        if entry.get("id"):
                            try:
                                _err = str(e)[:200]
                                if is_key_exhausted_error(_err):
                                    await mark_key_failed(entry["id"], _err)
                            except Exception:
                                pass
            except Exception:
                pass

        if provider and provider.value in self.clients:
            prov = provider
        else:
            prov = self._get_next_provider()
        if prov is None:
            raise Exception("No healthy LLM providers available")

        config = PROVIDER_CONFIG[prov]
        client = self.clients.get(prov.value)
        actual_model = model or config["default_model"]

        try:
            try:
                stream = await client.chat.completions.create(
                    model=actual_model, messages=messages, temperature=temp,
                    max_tokens=max_tok, stream=True,
                    stream_options={"include_usage": True},
                )
            except Exception:
                stream = await client.chat.completions.create(
                    model=actual_model, messages=messages, temperature=temp,
                    max_tokens=max_tok, stream=True,
                )
            _usage = None
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    _usage = chunk.usage
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield {"content": delta.content, "provider": prov.value, "model": actual_model}
            if _usage:
                yield {"__usage__": {
                    "provider": prov.value, "model": actual_model,
                    "tokens_in": getattr(_usage, "prompt_tokens", 0) or 0,
                    "tokens_out": getattr(_usage, "completion_tokens", 0) or 0,
                }}
        except Exception as e:
            self._mark_failed(prov.value)
            raise


llm_gateway = LLMGateway()
