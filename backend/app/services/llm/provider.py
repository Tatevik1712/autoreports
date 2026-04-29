"""
Абстракция над LLM-провайдерами.
Переключение между Ollama / OpenAI / Anthropic — только через ENV.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Protocol

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Результат вызова LLM
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMResult:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Протокол (интерфейс) — любой провайдер должен реализовать
# ─────────────────────────────────────────────────────────────────────────────

class LLMProvider(Protocol):
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult: ...


# ─────────────────────────────────────────────────────────────────────────────
# Ollama / OpenAI-compatible (через LangChain ChatOpenAI)
# ─────────────────────────────────────────────────────────────────────────────

class OllamaOpenAIProvider:
    """
    Работает с Ollama (local) и любым OpenAI-совместимым API.
    Ollama поддерживает OpenAI API с base_url=http://ollama:11434/v1
    """

    def __init__(self) -> None:
        base_url = settings.llm_base_url
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        self._client = ChatOpenAI(
            model=settings.llm_model,
            base_url=base_url,
            api_key=settings.llm_api_key or "ollama",   # Ollama принимает любой ключ
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
            max_retries=2,
        )
        self._model_name = settings.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        kwargs: dict = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        t0 = time.perf_counter()

        # Не логируем содержимое промптов — только метаданные
        logger.debug(
            "llm_request",
            model=self._model_name,
            system_len=len(system_prompt),
            user_len=len(user_prompt),
        )

        response = await self._client.ainvoke(messages, **kwargs)
        latency = time.perf_counter() - t0

        usage = getattr(response, "usage_metadata", {}) or {}
        result = LLMResult(
            content=str(response.content),
            model=self._model_name,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            latency_seconds=round(latency, 2),
        )

        logger.info(
            "llm_response",
            model=self._model_name,
            latency=result.latency_seconds,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic (нативный клиент)
# ─────────────────────────────────────────────────────────────────────────────

class AnthropicProvider:
    def __init__(self) -> None:
        import anthropic
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout,
        )
        self._model_name = settings.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        t0 = time.perf_counter()

        response = await self._client.messages.create(
            model=self._model_name,
            max_tokens=max_tokens or settings.llm_max_tokens,
            temperature=temperature if temperature is not None else settings.llm_temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        latency = time.perf_counter() - t0
        content = response.content[0].text if response.content else ""

        return LLMResult(
            content=content,
            model=self._model_name,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            latency_seconds=round(latency, 2),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Фабрика
# ─────────────────────────────────────────────────────────────────────────────

def create_llm_provider() -> LLMProvider:
    provider = settings.llm_provider
    logger.info("llm_provider_init", provider=provider, model=settings.llm_model)

    if provider in ("ollama", "openai"):
        return OllamaOpenAIProvider()
    if provider == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"Неизвестный LLM провайдер: {provider}")


# Синглтон — создаётся один раз при старте приложения
_llm_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = create_llm_provider()
    return _llm_provider
