import time
import logging
from enum import Enum
from typing import AsyncIterator
from dataclasses import dataclass, field
from openai import AsyncOpenAI
from app.core.config import get_settings

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
        "api_key": settings.fireworks_api_key,
        "base_url": settings.fireworks_base_url,
        "default_model": "accounts/fireworks/models/deepseek-v4-pro",
    },
    Provider.OPENAI: {
        "api_key": settings.openai_api_key,
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    Provider.GROQ: {
        "api_key": settings.groq_api_key,
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
    ) -> LLMResponse:
        start_time = time.time()
        temp = temperature if temperature is not None else settings.temperature
        max_tok = max_tokens if max_tokens is not None else settings.max_tokens

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
    ) -> AsyncIterator[dict]:
        temp = temperature if temperature is not None else settings.temperature
        max_tok = max_tokens if max_tokens is not None else settings.max_tokens

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
            stream = await client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temp,
                max_tokens=max_tok,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield {"content": delta.content, "provider": prov.value, "model": actual_model}
        except Exception as e:
            self._mark_failed(prov.value)
            raise


llm_gateway = LLMGateway()
