"""
VectorStore v2 — хранит child-текст для поиска, parent-текст для контекста.

При запросе возвращает parent_text (богатый контекст) вместо child_text.
Это ключевое для точности: ищем по точному фрагменту, читаем широкий контекст.
"""
from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.rag.chunker import Chunk, ChunkType

logger = get_logger(__name__)
settings = get_settings()

CHROMA_PATH = "/app/data/chromadb"


class VectorStore:
    def __init__(self, collection_name: str) -> None:
        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        ids        = [c.id for c in chunks]
        # В ChromaDB идёт child_text — для точного поиска
        documents  = [c.text for c in chunks]
        metadatas  = [
            {
                "source_file_id":  c.source_file_id,
                "source_filename": c.source_filename,
                "page":            c.page,
                "section":         c.section,
                "chunk_type":      c.chunk_type.value,
                "chunk_index":     c.chunk_index,
                # parent_text сохраняем в метаданных — именно его отдадим в LLM
                "parent_text":     c.parent_text[:4000],
                "priority": 2 if c.chunk_type in (ChunkType.table, ChunkType.numeric) else 1,
            }
            for c in chunks
        ]
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug("vector_store_indexed", collection=self._collection_name, count=len(chunks))

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 15,
        where: dict | None = None,
    ) -> list[SearchResult]:
        n = min(n_results, self._collection.count() or 1)
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": n,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)
        results: list[SearchResult] = []

        for i, child_text in enumerate(raw["documents"][0]):
            meta     = raw["metadatas"][0][i]
            distance = raw["distances"][0][i]
            score    = 1.0 - (distance / 2.0)

            # Отдаём parent_text — богатый контекст
            parent_text = meta.get("parent_text") or child_text

            results.append(SearchResult(
                child_text      = child_text,
                text            = parent_text,
                score           = score,
                source_file_id  = meta.get("source_file_id", ""),
                source_filename = meta.get("source_filename", ""),
                page            = int(meta.get("page", 0)),
                section         = meta.get("section", ""),
                chunk_type      = ChunkType(meta.get("chunk_type", "text")),
                chunk_index     = int(meta.get("chunk_index", 0)),
                priority        = int(meta.get("priority", 1)),
            ))
        return results

    def delete_collection(self) -> None:
        self._client.delete_collection(self._collection_name)
        logger.info("vector_store_deleted", collection=self._collection_name)

    @property
    def count(self) -> int:
        return self._collection.count()


class SearchResult:
    __slots__ = (
        "child_text", "text", "score",
        "source_file_id", "source_filename",
        "page", "section", "chunk_type", "chunk_index", "priority",
        "bm25_score", "rrf_score", "rerank_score",
    )

    def __init__(
        self,
        child_text: str,
        text: str,
        score: float,
        source_file_id: str,
        source_filename: str,
        page: int,
        section: str,
        chunk_type: ChunkType,
        chunk_index: int,
        priority: int = 1,
    ) -> None:
        self.child_text      = child_text
        self.text            = text       # parent_text → в LLM
        self.score           = score
        self.source_file_id  = source_file_id
        self.source_filename = source_filename
        self.page            = page
        self.section         = section
        self.chunk_type      = chunk_type
        self.chunk_index     = chunk_index
        self.priority        = priority
        self.bm25_score: float    = 0.0
        self.rrf_score: float     = 0.0
        self.rerank_score: float  = 0.0

    @property
    def source_label(self) -> str:
        parts = [self.source_filename]
        if self.page:
            parts.append(f"стр. {self.page}")
        if self.section:
            parts.append(self.section[:60])
        return " / ".join(parts)

    def __repr__(self) -> str:
        return (
            f"SearchResult(rrf={self.rrf_score:.3f}, "
            f"rerank={self.rerank_score:.3f}, "
            f"file={self.source_filename}, page={self.page})"
        )


def get_vector_store(collection_name: str) -> VectorStore:
    return VectorStore(collection_name)
