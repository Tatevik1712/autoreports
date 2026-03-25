"""
Hybrid Retriever v2 — RRF + LLM Cross-Encoder Reranking.

Pipeline:
  1. Dense (ChromaDB, top-30) + Sparse (BM25, top-30)
  2. RRF слияние → top-20 кандидатов
  3. Cross-encoder reranking через LLM (оценивает релевантность 0-10)
  4. Финальный top-k с учётом score и priority

Cross-encoder (шаг 3) — ключевое улучшение для точности:
  bi-encoder (эмбеддинги) хорошо отсеивает нерелевантное,
  но плохо разбирает нюансы. LLM-reranker смотрит на пары
  (запрос, чанк) и выдаёт точный score.

Для таблиц и числовых чанков — отдельный targeted поиск
перед основным (гарантирует попадание числовых данных).
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from backend.app.core.logging import get_logger
from backend.app.services.rag.chunker import Chunk, ChunkType
from backend.app.services.rag.vector_store import SearchResult

logger = get_logger(__name__)

RRF_K          = 60
TOP_DENSE      = 30   # увеличено для точности
TOP_SPARSE     = 30
RERANK_TOP     = 20   # кандидаты для reranking
FINAL_TOP_K    = 12   # финал после reranking
CONTEXT_WINDOW = 1    # ±1 соседний чанк

# Если True — включает LLM reranking (медленнее, но точнее)
# Выключается автоматически если LLM недоступен
RERANKING_ENABLED = True


class HybridRetriever:
    """RRF + опциональный LLM cross-encoder reranking."""

    async def fuse_and_rerank(
        self,
        query: str,
        dense_results: list[SearchResult],
        sparse_results: list[tuple[str, float]],
        all_chunks_by_id: dict[str, Chunk],
        top_k: int = FINAL_TOP_K,
        llm=None,   # LLMProvider — нужен для reranking
    ) -> list[SearchResult]:
        """
        Полный pipeline: RRF → expand neighbors → rerank → top_k.
        """
        # ── 1. RRF слияние ────────────────────────────────────────────────
        rrf_scores: dict[str, float]   = defaultdict(float)
        dense_by_id: dict[str, SearchResult] = {}

        for rank, result in enumerate(dense_results):
            cid = _result_id(result)
            rrf_scores[cid] += 1.0 / (RRF_K + rank + 1)
            dense_by_id[cid] = result

        for rank, (cid, _) in enumerate(sparse_results):
            rrf_scores[cid] += 1.0 / (RRF_K + rank + 1)

        # ── 2. Буст таблиц и числовых чанков ─────────────────────────────
        for cid, result in dense_by_id.items():
            if result.chunk_type in (ChunkType.table, ChunkType.numeric):
                rrf_scores[cid] *= 1.6

        # ── 3. Сортировка → кандидаты для reranking ───────────────────────
        sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
        candidate_ids = sorted_ids[:RERANK_TOP]

        # ── 4. Расширение соседями ────────────────────────────────────────
        expanded_ids = _expand_neighbors(candidate_ids, all_chunks_by_id)

        # ── 5. Собираем объекты ───────────────────────────────────────────
        candidates: list[SearchResult] = []
        for cid in expanded_ids:
            if cid in dense_by_id:
                r = dense_by_id[cid]
            elif cid in all_chunks_by_id:
                ch = all_chunks_by_id[cid]
                r = SearchResult(
                    child_text=ch.text, text=ch.parent_text,
                    score=rrf_scores.get(cid, 0.0),
                    source_file_id=ch.source_file_id,
                    source_filename=ch.source_filename,
                    page=ch.page, section=ch.section,
                    chunk_type=ch.chunk_type, chunk_index=ch.chunk_index,
                    priority=2 if ch.chunk_type in (ChunkType.table, ChunkType.numeric) else 1,
                )
            else:
                continue
            r.rrf_score = rrf_scores.get(cid, 0.0)
            candidates.append(r)

        # ── 6. LLM cross-encoder reranking ────────────────────────────────
        if RERANKING_ENABLED and llm is not None and len(candidates) > top_k:
            candidates = await _llm_rerank(query, candidates, llm, top_k=top_k * 2)

        # ── 7. Финальная сортировка и top_k ───────────────────────────────
        candidates.sort(
            key=lambda r: (r.rerank_score if r.rerank_score > 0 else r.rrf_score),
            reverse=True,
        )
        result_list = candidates[:top_k]

        logger.debug(
            "hybrid_retrieval_done",
            dense=len(dense_results),
            sparse=len(sparse_results),
            candidates=len(candidates),
            final=len(result_list),
        )
        return result_list


# ── LLM Cross-Encoder Reranking ──────────────────────────────────────────────

_RERANK_SYSTEM = (
    "Ты — система оценки релевантности фрагментов документа. "
    "Отвечай ТОЛЬКО валидным JSON без markdown."
)

_RERANK_PROMPT = """\
Оцени, насколько каждый фрагмент релевантен для ответа на запрос.

ЗАПРОС: {query}

ФРАГМЕНТЫ:
{fragments}

Верни JSON:
{{
  "scores": [
    {{"index": 0, "score": 8, "reason": "содержит прямой ответ"}},
    {{"index": 1, "score": 3, "reason": "косвенно связан"}},
    ...
  ]
}}
score: 0 (нерелевантно) .. 10 (точный ответ). Оцени ВСЕ {n} фрагментов.
"""


async def _llm_rerank(
    query: str,
    candidates: list[SearchResult],
    llm,
    top_k: int,
) -> list[SearchResult]:
    """
    LLM оценивает релевантность каждого кандидата (0-10).
    Работает батчами по 10, чтобы не переполнить контекст.
    """
    BATCH = 10
    for i in range(0, len(candidates), BATCH):
        batch = candidates[i : i + BATCH]
        fragments_text = "\n\n".join(
            f"[{j}] {r.child_text[:400]}"   # child_text — короткий, для оценки
            for j, r in enumerate(batch)
        )
        prompt = _RERANK_PROMPT.format(
            query=query[:500],
            fragments=fragments_text,
            n=len(batch),
        )
        try:
            result = await llm.complete(
                system_prompt=_RERANK_SYSTEM,
                user_prompt=prompt,
                temperature=0.0,
                max_tokens=512,
            )
            raw = result.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
            for item in data.get("scores", []):
                idx = item.get("index", -1)
                score = float(item.get("score", 0))
                if 0 <= idx < len(batch):
                    batch[idx].rerank_score = score / 10.0   # нормализуем в [0,1]
        except Exception as exc:
            logger.warning("rerank_failed", error=str(exc), batch_start=i)
            # Если reranking упал — оставляем rrf_score

    # Сортируем по rerank_score (если есть) или rrf_score
    candidates.sort(
        key=lambda r: r.rerank_score if r.rerank_score > 0 else r.rrf_score,
        reverse=True,
    )
    return candidates[:top_k]


# ── Вспомогательные функции ──────────────────────────────────────────────────

def _result_id(result: SearchResult) -> str:
    return f"{result.source_file_id}:{result.chunk_index}"


def _expand_neighbors(
    top_ids: list[str],
    all_chunks_by_id: dict[str, Chunk],
) -> list[str]:
    if CONTEXT_WINDOW == 0:
        return top_ids

    index_map: dict[tuple[str, int], str] = {
        (ch.source_file_id, ch.chunk_index): cid
        for cid, ch in all_chunks_by_id.items()
    }

    expanded = list(top_ids)
    seen = set(top_ids)

    for cid in top_ids:
        if cid not in all_chunks_by_id:
            continue
        ch = all_chunks_by_id[cid]
        if ch.chunk_type == ChunkType.table:
            continue   # таблицы самодостаточны
        for delta in range(-CONTEXT_WINDOW, CONTEXT_WINDOW + 1):
            if delta == 0:
                continue
            nbr = index_map.get((ch.source_file_id, ch.chunk_index + delta))
            if nbr and nbr not in seen:
                expanded.append(nbr)
                seen.add(nbr)

    return expanded


def get_hybrid_retriever() -> HybridRetriever:
    return HybridRetriever()
