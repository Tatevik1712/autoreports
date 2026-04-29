"""
Chunker v2 — Parent-Child стратегия для документов 20–100 стр.

Идея: два уровня чанков из одного и того же текста:
  - child  (400 симв.) → индексируется в ChromaDB, используется для поиска
  - parent (1200 симв.) → хранится in-memory, передаётся в LLM как контекст

Это даёт точный поиск (маленький чанк = меньше шума в эмбеддинге)
и богатый контекст для генерации (большой чанк = меньше обрывов мысли).

Таблицы — всегда отдельные чанки, не режутся и не участвуют в parent-child.
Числовые блоки — помечаются ChunkType.numeric, получают буст в ретривере.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
import re

from app.core.logging import get_logger
from app.services.document.parser import ParsedDocument

logger = get_logger(__name__)

# ── Константы (настроены под 20-100 стр., приоритет точности) ────────────────
CHILD_CHUNK_SIZE  = 400    # child → в ChromaDB (поиск)
PARENT_CHUNK_SIZE = 1200   # parent → в LLM (контекст)
CHUNK_OVERLAP     = 200    # overlap для child-чанков
MIN_CHUNK_SIZE    = 60
MAX_TABLE_CHUNK   = 4000   # таблицы больше этого — режем по строкам


class ChunkType(StrEnum):
    text    = "text"
    table   = "table"
    heading = "heading"
    numeric = "numeric"   # содержит числа/единицы — буст при поиске


@dataclass
class Chunk:
    """Единица индексации и поиска."""
    id: str
    text: str                  # child-текст (для embedding)
    parent_text: str           # parent-текст (для промпта LLM)
    chunk_type: ChunkType
    source_file_id: str
    source_filename: str
    page: int        = 0
    section: str     = ""
    chunk_index: int = 0
    meta: dict       = field(default_factory=dict)

    @property
    def source_label(self) -> str:
        parts = [self.source_filename]
        if self.page:
            parts.append(f"стр. {self.page}")
        if self.section:
            parts.append(self.section[:60])
        return " / ".join(parts)


# ── Паттерны ─────────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(
    r"^(?:"
    r"#{1,4}\s+"
    r"|(?:\d+\.){1,3}\s+[А-ЯA-Z\w]"
    r"|[А-ЯЁ][А-ЯЁ\s]{4,}$"
    r")",
    re.MULTILINE,
)

# Числа с единицами измерения, %, формулами
_NUMERIC_RE = re.compile(
    r"\d+[.,]\d+|\d+\s*(?:%|кг|мм|км|МПа|кДж|°C|м/с|т\.п\.|шт\.|"
    r"ед\.|мл|л\b|кВт|Вт|А\b|В\b|Гц|нм|мкм|мин\b|ч\b|сут\.?)",
    re.IGNORECASE,
)

# ГОСТ, ОСТ, СНиП, РД, СП — нормативные ссылки
_NORMATIVE_RE = re.compile(
    r"\b(?:ГОСТ|ОСТ|СНиП|РД|СП|ТУ|МИ|ПНД|ИСО|ISO|EN\s)\s*[\d\-\.]+",
    re.IGNORECASE,
)


class DocumentChunker:
    """
    Разбивает ParsedDocument на Chunk-и по parent-child стратегии.
    """

    def chunk(self, doc: ParsedDocument, source_file_id: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        idx = 0

        # ── 1. Таблицы — отдельные чанки ─────────────────────────────────
        for t_idx, table in enumerate(doc.tables):
            table_text = _table_to_text(table)
            if len(table_text) < MIN_CHUNK_SIZE:
                continue
            for sub_idx, part in enumerate(_split_large_table(table, table_text)):
                chunks.append(Chunk(
                    id=f"{source_file_id}:tbl:{t_idx}:{sub_idx}",
                    text=part,
                    parent_text=part,   # таблица — parent == child
                    chunk_type=ChunkType.table,
                    source_file_id=source_file_id,
                    source_filename=doc.filename,
                    chunk_index=idx,
                    meta={"table_index": t_idx, "rows": len(table)},
                ))
                idx += 1

        # ── 2. Текстовые чанки постранично ───────────────────────────────
        for page_num, page_text in enumerate(doc.pages, start=1):
            if not page_text.strip():
                continue

            page_chunks = list(_chunk_page_parent_child(
                text=page_text,
                page=page_num,
                source_file_id=source_file_id,
                source_filename=doc.filename,
                start_idx=idx,
            ))
            for ch in page_chunks:
                ch.chunk_index = idx
                chunks.append(ch)
                idx += 1

        logger.debug(
            "document_chunked",
            filename=doc.filename,
            total=len(chunks),
            tables=sum(1 for c in chunks if c.chunk_type == ChunkType.table),
            numeric=sum(1 for c in chunks if c.chunk_type == ChunkType.numeric),
        )
        return chunks


# ── Основная логика чанкинга ─────────────────────────────────────────────────

def _chunk_page_parent_child(
    text: str,
    page: int,
    source_file_id: str,
    source_filename: str,
    start_idx: int,
) -> Iterator[Chunk]:
    """
    Для одной страницы:
    1. Нарезаем на parent-блоки (PARENT_CHUNK_SIZE)
    2. Каждый parent режем на child-чанки (CHILD_CHUNK_SIZE)
    3. Каждый child знает своего parent
    """
    paragraphs = _split_by_structure(text)
    current_section = ""

    # Сначала собираем parent-блоки
    parent_blocks: list[tuple[str, str]] = []   # (section, parent_text)
    parent_buf: list[str] = []
    parent_len = 0

    def flush_parent() -> None:
        nonlocal parent_buf, parent_len
        block = "\n".join(parent_buf).strip()
        if len(block) >= MIN_CHUNK_SIZE:
            parent_blocks.append((current_section, block))
        parent_buf = []
        parent_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if _HEADING_RE.match(para):
            flush_parent()
            current_section = para[:100]
            # Заголовок — короткий отдельный chunk
            yield Chunk(
                id=f"{source_file_id}:h{page}:{start_idx}",
                text=para,
                parent_text=para,
                chunk_type=ChunkType.heading,
                source_file_id=source_file_id,
                source_filename=source_filename,
                page=page,
                section=current_section,
            )
            continue

        if parent_len + len(para) > PARENT_CHUNK_SIZE and parent_buf:
            flush_parent()
            # overlap на уровне parent
            tail = _take_tail("\n".join(parent_buf) if parent_buf else para, CHUNK_OVERLAP)
            if tail:
                parent_buf = [tail]
                parent_len = len(tail)

        parent_buf.append(para)
        parent_len += len(para)

    flush_parent()

    # Теперь режем каждый parent на child-чанки
    local_idx = start_idx
    for section, parent_text in parent_blocks:
        children = list(_split_into_children(parent_text))
        for child_text in children:
            chunk_type = _classify(child_text)
            yield Chunk(
                id=f"{source_file_id}:p{page}:{local_idx}",
                text=child_text,
                parent_text=parent_text,   # ← весь parent идёт в LLM
                chunk_type=chunk_type,
                source_file_id=source_file_id,
                source_filename=source_filename,
                page=page,
                section=section,
            )
            local_idx += 1


def _split_into_children(parent_text: str) -> Iterator[str]:
    """Режет parent на child-чанки с overlap."""
    text = parent_text
    while len(text) > CHILD_CHUNK_SIZE:
        yield text[:CHILD_CHUNK_SIZE]
        # overlap: не теряем граничный контекст
        text = text[CHILD_CHUNK_SIZE - CHUNK_OVERLAP:]
    if len(text) >= MIN_CHUNK_SIZE:
        yield text


def _classify(text: str) -> ChunkType:
    """Определяет тип чанка по содержимому."""
    if _NUMERIC_RE.search(text) or _NORMATIVE_RE.search(text):
        return ChunkType.numeric
    return ChunkType.text


def _split_by_structure(text: str) -> list[str]:
    parts = re.split(r"\n{2,}", text)
    result: list[str] = []
    for part in parts:
        if len(part) > PARENT_CHUNK_SIZE * 2:
            result.extend(part.split("\n"))
        else:
            result.append(part)
    return result


def _take_tail(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    tail = text[-n:]
    space = tail.find(" ")
    return tail[space + 1:] if space != -1 else tail


def _table_to_text(table: list[list[str]]) -> str:
    if not table:
        return ""
    lines = []
    if table:
        lines.append(" | ".join(str(c) for c in table[0]))
        lines.append("-" * 40)
    for row in table[1:]:
        lines.append(" | ".join(str(c) for c in row))
    return "\n".join(lines)


def _split_large_table(table: list[list[str]], full_text: str) -> list[str]:
    if len(full_text) <= MAX_TABLE_CHUNK:
        return [full_text]
    header = table[0] if table else []
    header_text = " | ".join(str(c) for c in header) + "\n" + "-" * 40 + "\n"
    parts: list[str] = []
    current = header_text
    for row in table[1:]:
        row_text = " | ".join(str(c) for c in row) + "\n"
        if len(current) + len(row_text) > MAX_TABLE_CHUNK and len(current) > len(header_text):
            parts.append(current.strip())
            current = header_text + row_text
        else:
            current += row_text
    if current.strip() != header_text.strip():
        parts.append(current.strip())
    return parts or [full_text]


def get_chunker() -> DocumentChunker:
    return DocumentChunker()
