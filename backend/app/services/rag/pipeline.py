"""
RAG Pipeline v2 — оптимизирован для стадии 1 (преобразование готового отчёта).

Новое по сравнению с v1:
1. Document Map — при индексации строим структурный обзор документа
   (разделы + их краткое содержание). Используется как "якорь" для генерации.

2. Targeted Table Search — перед основным поиском специально ищем
   таблицы и числовые блоки по секции. Гарантирует попадание цифр в контекст.

3. LLM Cross-Encoder Reranking — второй проход через LLM для точной
   оценки релевантности кандидатов.

4. RetrievalDebugger — структурированный лог: какие чанки попали в промпт,
   их score, откуда они. Доступен через API для диагностики.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.services.document.parser import ParsedDocument
from app.services.rag.bm25_retriever import BM25Retriever
from app.services.rag.chunker import Chunk, ChunkType, get_chunker
from app.services.rag.context_builder import BuiltContext, get_context_builder
from app.services.rag.embeddings import get_embedding_service
from app.services.rag.hybrid_retriever import get_hybrid_retriever
from app.services.rag.vector_store import SearchResult, get_vector_store

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Debug-структуры
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChunkDebugInfo:
    chunk_id: str
    source_filename: str
    page: int
    section: str
    chunk_type: str
    rrf_score: float
    rerank_score: float
    text_preview: str   # первые 120 символов child_text

@dataclass
class RetrievalDebugInfo:
    query: str
    dense_count: int
    sparse_count: int
    final_count: int
    chunks: list[ChunkDebugInfo]
    table_chunks_count: int
    context_chars: int
    truncated: bool


@dataclass
class IndexingStats:
    total_docs: int
    indexed_docs: int
    total_chunks: int
    table_chunks: int
    numeric_chunks: int
    errors: list[str]
    document_map: str = ""   # структурный обзор документов

    def __repr__(self) -> str:
        return (
            f"IndexingStats(docs={self.indexed_docs}/{self.total_docs}, "
            f"chunks={self.total_chunks}, tables={self.table_chunks}, "
            f"numeric={self.numeric_chunks})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class RAGPipeline:
    """
    RAG pipeline v2 — стадия 1, приоритет точности.
    """

    def __init__(self, collection_id: str) -> None:
        self._collection_id    = f"report_{collection_id}"
        self._vector_store     = get_vector_store(self._collection_id)
        self._embed_service    = get_embedding_service()
        self._hybrid_retriever = get_hybrid_retriever()
        self._context_builder  = get_context_builder()
        self._chunker          = get_chunker()

        self._all_chunks: list[Chunk]       = []
        self._chunks_by_id: dict[str, Chunk] = {}
        self._bm25: BM25Retriever | None    = None
        self._indexed = False
        self._document_map = ""      # структурный обзор всех документов

        # История поисков для дебага
        self._retrieval_log: list[RetrievalDebugInfo] = []

    # ── Индексация ────────────────────────────────────────────────────────────

    async def index(self, docs: list[ParsedDocument]) -> IndexingStats:
        logger.info(
            "rag_index_start",
            collection=self._collection_id,
            docs=len(docs),
        )

        errors: list[str] = []
        total_chunks = table_chunks = numeric_chunks = 0

        for doc in docs:
            if doc.error:
                errors.append(f"{doc.filename}: {doc.error}")
                logger.warning("rag_skip_doc", filename=doc.filename, error=doc.error)
                continue

            chunks = self._chunker.chunk(doc, source_file_id=doc.filename)
            if not chunks:
                logger.warning("rag_no_chunks", filename=doc.filename)
                continue

            # Батчевые эмбеддинги — только child_text
            child_texts = [c.text for c in chunks]
            embeddings = await self._embed_service.embed_texts(child_texts)

            self._vector_store.add_chunks(chunks, embeddings)

            for ch in chunks:
                self._all_chunks.append(ch)
                self._chunks_by_id[ch.id] = ch

            total_chunks   += len(chunks)
            table_chunks   += sum(1 for c in chunks if c.chunk_type == ChunkType.table)
            numeric_chunks += sum(1 for c in chunks if c.chunk_type == ChunkType.numeric)

            logger.info("rag_doc_indexed", filename=doc.filename, chunks=len(chunks))

        # BM25 по child_text (точный текст лучше для keyword search)
        if self._all_chunks:
            self._bm25 = BM25Retriever(
                all_chunks_text=[c.text for c in self._all_chunks],
                all_chunk_ids=[c.id for c in self._all_chunks],
            )

        # Document map — строим структурный обзор
        self._document_map = _build_document_map(self._all_chunks, docs)

        self._indexed = True

        stats = IndexingStats(
            total_docs=len(docs),
            indexed_docs=len(docs) - len(errors),
            total_chunks=total_chunks,
            table_chunks=table_chunks,
            numeric_chunks=numeric_chunks,
            errors=errors,
            document_map=self._document_map,
        )
        logger.info("rag_index_done", stats=repr(stats))
        return stats

    # ── Поиск ─────────────────────────────────────────────────────────────────

    async def retrieve_for_section(
        self,
        section_title: str,
        section_description: str,
        section_rules: list[str],
        top_k: int = 12,
        llm=None,
    ) -> BuiltContext:
        """
        Многоэтапный поиск для секции шаблона:
        1. Targeted table/numeric search (всегда)
        2. Основной гибридный поиск
        3. Дедупликация и слияние
        """
        if not self._indexed:
            raise RuntimeError("Вызовите index() перед retrieve_for_section()")

        # Составной запрос
        query = _build_section_query(section_title, section_description, section_rules)

        # ── Step 1: Targeted поиск таблиц ────────────────────────────────
        table_results = await self._search_tables(query, n=4)

        # ── Step 2: Основной гибридный поиск ─────────────────────────────
        query_emb = await self._embed_service.embed_query(query)

        dense = self._vector_store.search(query_emb, n_results=30)
        sparse = self._bm25.search(query, n_results=30) if self._bm25 else []

        fused = await self._hybrid_retriever.fuse_and_rerank(
            query=query,
            dense_results=dense,
            sparse_results=sparse,
            all_chunks_by_id=self._chunks_by_id,
            top_k=top_k,
            llm=llm,
        )

        # ── Step 3: Объединяем с table_results (без дублей) ──────────────
        seen_ids = {_result_id(r) for r in fused}
        for tr in table_results:
            if _result_id(tr) not in seen_ids:
                fused.append(tr)
                seen_ids.add(_result_id(tr))

        # ── Debug log ─────────────────────────────────────────────────────
        context = self._context_builder.build(fused)
        self._log_retrieval(query, dense, sparse, fused, context)

        return context

    async def _search_tables(self, query: str, n: int = 4) -> list[SearchResult]:
        """Целевой поиск только по таблицам и числовым блокам."""
        query_emb = await self._embed_service.embed_query(query)
        results = self._vector_store.search(
            query_emb,
            n_results=n * 3,
            where={"chunk_type": {"$in": ["table", "numeric"]}},
        )
        # Сортируем по score и берём top-n
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:n]

    # ── Document Map ─────────────────────────────────────────────────────────

    @property
    def document_map(self) -> str:
        """Структурный обзор проиндексированных документов."""
        return self._document_map

    # ── Debug ─────────────────────────────────────────────────────────────────

    @property
    def retrieval_log(self) -> list[RetrievalDebugInfo]:
        return self._retrieval_log

    def _log_retrieval(
        self,
        query: str,
        dense: list[SearchResult],
        sparse: list[tuple],
        final: list[SearchResult],
        context: BuiltContext,
    ) -> None:
        chunk_infos = [
            ChunkDebugInfo(
                chunk_id=_result_id(r),
                source_filename=r.source_filename,
                page=r.page,
                section=r.section,
                chunk_type=r.chunk_type.value,
                rrf_score=round(r.rrf_score, 4),
                rerank_score=round(r.rerank_score, 4),
                text_preview=r.child_text[:120],
            )
            for r in final
        ]
        self._retrieval_log.append(RetrievalDebugInfo(
            query=query[:200],
            dense_count=len(dense),
            sparse_count=len(sparse),
            final_count=len(final),
            chunks=chunk_infos,
            table_chunks_count=sum(1 for r in final if r.chunk_type == ChunkType.table),
            context_chars=len(context.text),
            truncated=context.truncated,
        ))

    # ── Управление жизненным циклом ───────────────────────────────────────────

    def cleanup(self, delete_collection: bool = False) -> None:
        self._all_chunks.clear()
        self._chunks_by_id.clear()
        self._bm25 = None
        self._retrieval_log.clear()
        if delete_collection:
            try:
                self._vector_store.delete_collection()
            except Exception as exc:
                logger.warning("rag_cleanup_error", error=str(exc))

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    @property
    def chunk_count(self) -> int:
        return len(self._all_chunks)


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _build_section_query(title: str, description: str, rules: list[str]) -> str:
    """Составной запрос: заголовок + описание + ключевые правила."""
    parts = [title, description] + rules[:2]
    return "\n".join(p for p in parts if p)


def _result_id(result: SearchResult) -> str:
    return f"{result.source_file_id}:{result.chunk_index}"


def _build_document_map(chunks: list[Chunk], docs: list[ParsedDocument]) -> str:
    """
    Строит текстовый структурный обзор документов:
    имена файлов → разделы → количество страниц/таблиц.
    Используется как "якорь" в промпте генерации.
    """
    lines = ["=== СТРУКТУРА ИСХОДНЫХ ДОКУМЕНТОВ ===\n"]

    # Группируем заголовки по файлу
    headings_by_file: dict[str, list[str]] = {}
    for ch in chunks:
        if ch.chunk_type == ChunkType.heading:
            headings_by_file.setdefault(ch.source_filename, []).append(ch.text.strip())

    for doc in docs:
        if doc.error:
            lines.append(f"📄 {doc.filename} [ОШИБКА: {doc.error}]")
            continue

        meta = doc.meta or {}
        page_info = f"{meta.get('page_count', len(doc.pages))} стр."
        table_info = f"{meta.get('table_count', len(doc.tables))} таблиц"
        lines.append(f"\n📄 {doc.filename}  ({page_info}, {table_info})")

        headings = headings_by_file.get(doc.filename, [])
        if headings:
            for h in headings[:15]:   # не больше 15 заголовков
                lines.append(f"   ├─ {h}")
            if len(headings) > 15:
                lines.append(f"   └─ ... ещё {len(headings) - 15} разделов")
        else:
            lines.append("   └─ (структура разделов не определена)")

    return "\n".join(lines)
