"""
Сборка контекста для LLM из найденных чанков.

Задача: из N разрозненных чанков собрать читаемый блок текста,
который помещается в окно контекста LLM и содержит метки источников.

Принципы:
1. Чанки группируются по файлу и разделу (не перемешиваем случайно)
2. Каждый фрагмент снабжён меткой [Источник: файл, стр. N]
3. Таблицы выделяются явно
4. Общий размер ограничен MAX_CONTEXT_CHARS
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.services.rag.chunker import ChunkType
from app.services.rag.vector_store import SearchResult

MAX_CONTEXT_CHARS = 12_000   # ~3000 токенов — оставляем место для промпта и ответа
MAX_SINGLE_CHUNK = 3_000     # ограничиваем один чанк


@dataclass
class BuiltContext:
    """Готовый контекст для вставки в промпт."""
    text: str                        # итоговый текст блока контекста
    sources: list[str]               # список меток источников (для transparency)
    chunk_count: int                 # сколько чанков вошло
    truncated: bool = False          # был ли контекст обрезан


class ContextBuilder:
    """
    Собирает блок контекста из списка SearchResult-ов.
    """

    def build(
        self,
        results: list[SearchResult],
        max_chars: int = MAX_CONTEXT_CHARS,
    ) -> BuiltContext:
        if not results:
            return BuiltContext(
                text="[Релевантные данные не найдены в исходных документах]",
                sources=[],
                chunk_count=0,
            )

        # ── 1. Группируем по файлу ────────────────────────────────────────
        by_file: dict[str, list[SearchResult]] = defaultdict(list)
        for r in results:
            by_file[r.source_filename].append(r)

        # ── 2. Внутри файла сортируем по позиции (chunk_index) ───────────
        for fname in by_file:
            by_file[fname].sort(key=lambda r: r.chunk_index)

        # ── 3. Собираем блок текста ───────────────────────────────────────
        parts: list[str] = []
        sources: list[str] = []
        total_len = 0
        chunk_count = 0
        truncated = False

        for filename, file_results in by_file.items():
            file_header = f"\n{'─' * 50}\n📄 Документ: {filename}\n{'─' * 50}"
            parts.append(file_header)
            total_len += len(file_header)

            current_section = None

            for result in file_results:
                # Заголовок раздела (если сменился)
                if result.section and result.section != current_section:
                    current_section = result.section
                    section_header = f"\n  📌 Раздел: {result.section}"
                    parts.append(section_header)
                    total_len += len(section_header)

                # Формируем блок чанка
                chunk_text = result.text[:MAX_SINGLE_CHUNK]
                if len(result.text) > MAX_SINGLE_CHUNK:
                    chunk_text += "\n  [... фрагмент обрезан ...]"

                # Метка источника
                page_info = f", стр. {result.page}" if result.page else ""
                source_label = f"[Источник: {filename}{page_info}]"

                # Формат для таблиц — явная разметка
                if result.chunk_type == ChunkType.table:
                    block = f"\n  {source_label}\n  📊 Таблица:\n{self._indent(chunk_text, 4)}\n"
                else:
                    block = f"\n  {source_label}\n{self._indent(chunk_text, 2)}\n"

                # Проверяем лимит
                if total_len + len(block) > max_chars:
                    truncated = True
                    break

                parts.append(block)
                total_len += len(block)
                chunk_count += 1

                label = f"{filename}{page_info}"
                if label not in sources:
                    sources.append(label)

            if truncated:
                break

        if truncated:
            parts.append(
                "\n\n⚠️  [Контекст обрезан из-за ограничения размера. "
                "Показаны наиболее релевантные фрагменты.]"
            )

        return BuiltContext(
            text="\n".join(parts),
            sources=sources,
            chunk_count=chunk_count,
            truncated=truncated,
        )

    @staticmethod
    def _indent(text: str, spaces: int) -> str:
        prefix = " " * spaces
        return "\n".join(prefix + line for line in text.splitlines())


def get_context_builder() -> ContextBuilder:
    return ContextBuilder()
