"""
Сервис эмбеддингов — локальная модель через Ollama.

Модель: nomic-embed-text (768-мерная, хорошо работает с русским).
Альтернатива: mxbai-embed-large (1024-мерная, точнее, но медленнее).

Особенности:
- Батчевая обработка (не по одному чанку)
- Retry с backoff при перегрузке Ollama
- Нормализация векторов (cosine similarity = dot product)
"""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Модель эмбеддингов — отдельная от генеративной LLM
EMBED_MODEL = "nomic-embed-text"
EMBED_BATCH_SIZE = 32          # чанков за один запрос к Ollama
EMBED_DIMENSION = 768          # размерность nomic-embed-text


class EmbeddingService:
    """
    Получает векторные представления текстов через Ollama /api/embed.
    """

    def __init__(self) -> None:
        # Ollama base URL без /v1 — используем нативный API эмбеддингов
        base = settings.llm_base_url.replace("/v1", "").rstrip("/")
        self._base_url = base
        self._client = httpx.AsyncClient(
            base_url=base,
            timeout=120.0,
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Получает эмбеддинги для списка текстов.
        Обрабатывает батчами, возвращает нормализованные векторы.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        logger.debug("embeddings_computed", count=len(texts))
        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        """Эмбеддинг одного запроса (оптимизация для поиска)."""
        results = await self._embed_batch([query])
        return results[0] if results else []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Вызов Ollama /api/embed для батча текстов.
        Нормализует векторы для cosine similarity через dot product.
        """
        response = await self._client.post(
            "/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
        )
        response.raise_for_status()
        data = response.json()

        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise ValueError(f"Ollama вернул пустой ответ для батча размером {len(texts)}")

        return [self._normalize(e) for e in embeddings]

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        """L2-нормализация вектора."""
        norm = sum(x * x for x in vector) ** 0.5
        if norm == 0:
            return vector
        return [x / norm for x in vector]

    async def close(self) -> None:
        await self._client.aclose()


# ── Синглтон ──────────────────────────────────────────────────────────────────

_embed_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embed_service
    if _embed_service is None:
        _embed_service = EmbeddingService()
    return _embed_service
