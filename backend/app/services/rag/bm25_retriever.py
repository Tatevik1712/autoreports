"""
BM25 — разреженный (ключевой) поиск.

Дополняет векторный поиск: хорошо находит точные термины, аббревиатуры,
номера стандартов (ГОСТ, ОСТ), числа — то, с чем векторный поиск хуже справляется.

Реализация: rank_bm25 (чистый Python, без внешних сервисов).
"""
from __future__ import annotations

import re

from app.core.logging import get_logger

logger = get_logger(__name__)

# Стоп-слова для русского + английского (минимальный набор)
_STOP_WORDS = frozenset({
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как",
    "а", "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у",
    "же", "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот",
    "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда",
    "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть",
    "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь",
    "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где",
    "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была",
    "сам", "чтоб", "без", "будто", "чего", "раз", "тоже", "себе", "под",
    "будет", "ж", "тогда", "кто", "этот", "того", "потому", "этого",
    "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой",
    "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех",
    "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть",
    # English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "to", "of", "in", "for", "on", "with", "as", "by", "at", "from",
})


def tokenize(text: str) -> list[str]:
    """
    Токенизация для BM25: lowercase, убираем пунктуацию, стоп-слова.
    Сохраняем числа и аббревиатуры (ГОСТ, ОСТ и т.п.).
    """
    text = text.lower()
    # Убираем пунктуацию, кроме дефиса внутри слова
    text = re.sub(r"[^\w\s\-]", " ", text)
    tokens = text.split()
    return [
        t for t in tokens
        if t not in _STOP_WORDS and len(t) >= 2
    ]


class BM25Index:
    """
    BM25 индекс для набора чанков.
    Строится in-memory — для каждой задачи свой.
    """

    # BM25 параметры (стандартные)
    K1 = 1.5
    B = 0.75

    def __init__(self, chunks_text: list[str], chunk_ids: list[str]) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError("Установите rank_bm25: pip install rank-bm25") from exc

        self._chunk_ids = chunk_ids
        self._tokenized = [tokenize(t) for t in chunks_text]
        self._bm25 = BM25Okapi(self._tokenized, k1=self.K1, b=self.B)
        logger.debug("bm25_index_built", docs=len(chunk_ids))

    def search(self, query: str, n_results: int = 10) -> list[tuple[str, float]]:
        """
        Возвращает список (chunk_id, normalized_score).
        """
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Нормализуем: score / max_score → [0, 1]
        max_score = max(scores) if max(scores) > 0 else 1.0
        normalized = [(self._chunk_ids[i], float(s) / max_score) for i, s in enumerate(scores)]

        # Сортируем и берём top-N
        normalized.sort(key=lambda x: x[1], reverse=True)
        return normalized[:n_results]


class BM25Retriever:
    """
    Retriever, построенный на BM25Index поверх набора SearchResult-ов.
    Добавляет bm25_score к уже найденным результатам и может вернуть новые.
    """

    def __init__(self, all_chunks_text: list[str], all_chunk_ids: list[str]) -> None:
        self._ids = all_chunk_ids
        self._text_map = dict(zip(all_chunk_ids, all_chunks_text, strict=True))
        self._index = BM25Index(all_chunks_text, all_chunk_ids)

    def search(self, query: str, n_results: int = 10) -> list[tuple[str, float]]:
        """Возвращает (chunk_id, bm25_score)."""
        return self._index.search(query, n_results)
