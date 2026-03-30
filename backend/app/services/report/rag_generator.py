"""
RAG Generator v2 — стадия 1 (преобразование готового отчёта под шаблон).

Отличия от v1:
1. Document Map в системном промпте — LLM знает структуру источника
2. Reranking через LLM — более точный отбор фрагментов
3. Адаптивный top_k — по типу секции
4. Retrieval debug — сохраняется в результате для API
5. Чёткое разделение: ДАННЫЕ ОТСУТСТВУЮТ vs ДАННЫЕ НЕПОЛНЫЕ
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from jinja2 import Template

from app.core.logging import get_logger
from app.schemas.schemas import TemplateSchema, TemplateSection, ValidationErrorItem
from app.services.document.parser import ParsedDocument
from app.services.llm.provider import LLMProvider, LLMResult
from app.services.rag.context_builder import BuiltContext
from app.services.rag.pipeline import IndexingStats, RAGPipeline, RetrievalDebugInfo

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Промпты
# ─────────────────────────────────────────────────────────────────────────────

# Системный промпт содержит document map — LLM понимает откуда что брать
_SYSTEM_GENERATION = Template("""\
Ты — ассистент нормоконтроля, который переносит содержимое научно-технического отчёта в стандартизированный шаблон.

{{ document_map }}

═══ АБСОЛЮТНЫЕ ПРАВИЛА (нарушение недопустимо) ═══
1. Используй ТОЛЬКО информацию из блока «НАЙДЕННЫЕ ФРАГМЕНТЫ».
2. Если нужная информация ОТСУТСТВУЕТ — напиши строго: [ДАННЫЕ ОТСУТСТВУЮТ]
3. Если информация есть, но неполная — напиши текст и добавь: [ДАННЫЕ НЕПОЛНЫЕ: что именно]
4. Никогда не выдумывай цифры, даты, имена, ссылки на стандарты.
5. Стиль — научно-технический, третье лицо, прошедшее время.
6. Язык — русский.
7. Отвечай ТОЛЬКО текстом секции — без преамбул и метакомментариев.\
""")

_SECTION_PROMPT = Template("""\
ЗАДАЧА: Перенеси информацию из исходного отчёта в секцию «{{ section.title }}» шаблона.

ОПИСАНИЕ СЕКЦИИ:
{{ section.description }}

ТРЕБОВАНИЯ К СЕКЦИИ:
{% for rule in section.rules %}- {{ rule }}
{% endfor %}

НАЙДЕННЫЕ ФРАГМЕНТЫ ИЗ ИСХОДНОГО ОТЧЁТА:
{{ context.text }}

{% if context.sources %}
Источники: {{ context.sources | join(" | ") }}
{% endif %}
{% if context.truncated %}
⚠ Контекст частично обрезан — показаны наиболее релевантные фрагменты.
{% endif %}

Напиши текст секции «{{ section.title }}»:
""")

_VALIDATION_PROMPT = Template("""\
Проверь текст секции «{{ section.title }}» на соответствие требованиям нормоконтроля.

ТРЕБОВАНИЯ К СЕКЦИИ:
{% for rule in section.rules %}- {{ rule }}
{% endfor %}

ГЛОБАЛЬНЫЕ ТРЕБОВАНИЯ:
{% for rule in global_rules %}- {{ rule }}
{% endfor %}

ТЕКСТ СЕКЦИИ:
---
{{ section_text }}
---

Верни JSON (без markdown):
{
  "errors": [
    {
      "type": "grammar|style|structure|missing_data|incorrect_data",
      "message": "описание ошибки",
      "recommendation": "как исправить конкретно",
      "severity": "error|warning|info"
    }
  ]
}

Если ошибок нет — {"errors": []}.
""")


# ─────────────────────────────────────────────────────────────────────────────
# Результат
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GenerationResult:
    sections: dict[str, str]
    validation_errors: list[ValidationErrorItem]
    llm_result: LLMResult
    total_seconds: float
    indexing_stats: dict
    retrieval_debug: list[dict] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Генератор
# ─────────────────────────────────────────────────────────────────────────────

class RAGReportGenerator:

    def __init__(self, llm: LLMProvider, report_id: str) -> None:
        self._llm = llm
        self._report_id = report_id
        self._rag = RAGPipeline(collection_id=report_id)

    async def generate(
        self,
        template_schema: TemplateSchema,
        source_docs: list[ParsedDocument],
        params: dict[str, Any] | None = None,
    ) -> GenerationResult:
        t0 = time.perf_counter()

        logger.info(
            "rag_gen_start",
            report=self._report_id,
            sections=len(template_schema.sections),
            docs=len(source_docs),
        )

        # ── 1. Индексация ─────────────────────────────────────────────────
        indexing_stats: IndexingStats = await self._rag.index(source_docs)

        # Системный промпт включает document map
        system_prompt = _SYSTEM_GENERATION.render(
            document_map=self._rag.document_map,
        )

        generated_sections: dict[str, str] = {}
        all_errors: list[ValidationErrorItem] = []
        total_prompt_tokens = total_completion_tokens = 0
        last_model = ""

        # ── 2. Генерация секций ───────────────────────────────────────────
        for section in template_schema.sections:
            top_k = _adaptive_top_k(section)

            context = await self._rag.retrieve_for_section(
                section_title=section.title,
                section_description=section.description,
                section_rules=section.rules,
                top_k=top_k,
                llm=self._llm,   # передаём для reranking
            )

            user_prompt = _SECTION_PROMPT.render(
                section=section,
                context=context,
            )

            llm_result = await self._llm.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            section_text = llm_result.content.strip()
            generated_sections[section.id] = section_text
            last_model = llm_result.model
            total_prompt_tokens     += llm_result.prompt_tokens
            total_completion_tokens += llm_result.completion_tokens

            # Анализируем маркеры
            if "[ДАННЫЕ ОТСУТСТВУЮТ]" in section_text and section.required:
                all_errors.append(ValidationErrorItem(
                    type="missing_data",
                    section_id=section.id,
                    message=f"Секция «{section.title}»: данные не найдены в исходном документе",
                    recommendation=(
                        "Проверьте, что исходный отчёт содержит информацию "
                        f"для секции «{section.title}»."
                        + (f" Доступные источники: {', '.join(context.sources)}"
                           if context.sources else " Релевантные фрагменты не найдены.")
                    ),
                    severity="error",
                ))
            elif "[ДАННЫЕ НЕПОЛНЫЕ" in section_text:
                all_errors.append(ValidationErrorItem(
                    type="missing_data",
                    section_id=section.id,
                    message=f"Секция «{section.title}»: данные присутствуют частично",
                    recommendation="Дополните исходный документ недостающими данными",
                    severity="warning",
                ))

        # ── 3. Нормоконтроль ──────────────────────────────────────────────
        for section in template_schema.sections:
            text = generated_sections.get(section.id, "")
            if not text or "[ДАННЫЕ ОТСУТСТВУЮТ]" in text:
                continue

            validation_errors, llm_result = await self._validate_section(
                section=section,
                section_text=text,
                global_rules=template_schema.global_rules,
            )
            all_errors.extend(validation_errors)
            total_prompt_tokens     += llm_result.prompt_tokens
            total_completion_tokens += llm_result.completion_tokens

        # ── 4. Сериализуем debug-лог ──────────────────────────────────────
        retrieval_debug = [
            {
                "query":         d.query,
                "dense_count":   d.dense_count,
                "sparse_count":  d.sparse_count,
                "final_count":   d.final_count,
                "table_chunks":  d.table_chunks_count,
                "context_chars": d.context_chars,
                "truncated":     d.truncated,
                "chunks": [
                    {
                        "id":       c.chunk_id,
                        "file":     c.source_filename,
                        "page":     c.page,
                        "section":  c.section,
                        "type":     c.chunk_type,
                        "rrf":      c.rrf_score,
                        "rerank":   c.rerank_score,
                        "preview":  c.text_preview,
                    }
                    for c in d.chunks
                ],
            }
            for d in self._rag.retrieval_log
        ]

        # ── 5. Очистка (коллекцию оставляем для перегенерации) ────────────
        self._rag.cleanup(delete_collection=False)

        total_seconds = round(time.perf_counter() - t0, 2)

        logger.info(
            "rag_gen_done",
            report=self._report_id,
            sections=len(generated_sections),
            errors=len(all_errors),
            seconds=total_seconds,
        )

        return GenerationResult(
            sections=generated_sections,
            validation_errors=all_errors,
            llm_result=LLMResult(
                content="",
                model=last_model,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                latency_seconds=total_seconds,
            ),
            total_seconds=total_seconds,
            indexing_stats={
                "total_docs":    indexing_stats.total_docs,
                "indexed_docs":  indexing_stats.indexed_docs,
                "total_chunks":  indexing_stats.total_chunks,
                "table_chunks":  indexing_stats.table_chunks,
                "numeric_chunks":indexing_stats.numeric_chunks,
                "errors":        indexing_stats.errors,
                "document_map":  indexing_stats.document_map,
            },
            retrieval_debug=retrieval_debug,
        )

    async def _validate_section(
        self,
        section: TemplateSection,
        section_text: str,
        global_rules: list[str],
    ) -> tuple[list[ValidationErrorItem], LLMResult]:
        user_prompt = _VALIDATION_PROMPT.render(
            section=section,
            section_text=section_text[:8_000],
            global_rules=global_rules,
        )
        llm_result = await self._llm.complete(
            system_prompt=(
                "Ты — строгий эксперт нормоконтроля НТД. "
                "Отвечай ТОЛЬКО валидным JSON без markdown."
            ),
            user_prompt=user_prompt,
            temperature=0.0,
        )
        errors: list[ValidationErrorItem] = []
        try:
            raw = (
                llm_result.content.strip()
                .removeprefix("```json").removeprefix("```")
                .removesuffix("```").strip()
            )
            data = json.loads(raw)
            for e in data.get("errors", []):
                errors.append(ValidationErrorItem(
                    type=e.get("type", "unknown"),
                    section_id=section.id,
                    message=e.get("message", ""),
                    recommendation=e.get("recommendation", ""),
                    severity=e.get("severity", "warning"),
                ))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("validation_parse_error", section=section.id, error=str(exc))

        return errors, llm_result


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

_DATA_HEAVY = frozenset({
    "результат", "данны", "измерени", "таблиц", "расчёт",
    "формул", "методик", "испытан", "эксперимент", "показател",
    "значени", "параметр", "характеристик",
})


def _adaptive_top_k(section: TemplateSection) -> int:
    """Секции с числовыми данными требуют больше чанков."""
    combined = (section.title + " " + section.description).lower()
    if any(kw in combined for kw in _DATA_HEAVY):
        return 15
    return 10


def get_rag_report_generator(llm: LLMProvider, report_id: str) -> RAGReportGenerator:
    return RAGReportGenerator(llm=llm, report_id=report_id)
