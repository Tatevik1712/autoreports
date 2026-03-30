"""
Сервис генерации отчёта.
Оркестрирует: парсинг → промпт → LLM → валидация → сборка DOCX.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from jinja2 import Template

from app.core.logging import get_logger
from app.schemas.schemas import TemplateSchema, TemplateSection, ValidationErrorItem
from app.services.document.parser import ParsedDocument
from app.services.llm.provider import LLMProvider, LLMResult

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Результат генерации
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GenerationResult:
    sections: dict[str, str]          # section_id → сгенерированный текст
    validation_errors: list[ValidationErrorItem]
    llm_result: LLMResult
    total_seconds: float


# ─────────────────────────────────────────────────────────────────────────────
# Промпты (Jinja2 шаблоны)
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """Ты — ассистент по оформлению научно-технических отчётов (НТД/НИР).
Твоя задача: извлечь информацию из исходных документов и заполнить указанную секцию отчёта.

СТРОГИЕ ПРАВИЛА:
1. Используй ТОЛЬКО информацию из предоставленных документов.
2. Если информация отсутствует — явно укажи это: [ДАННЫЕ ОТСУТСТВУЮТ].
3. НЕ выдумывай факты, цифры, имена, даты.
4. Сохраняй профессиональный стиль научно-технического документа.
5. Отвечай на русском языке.
6. Отвечай ТОЛЬКО текстом секции без лишних пояснений и преамбул."""

_SECTION_PROMPT_TEMPLATE = Template("""
ЗАДАЧА: Заполни секцию «{{ section.title }}» научно-технического отчёта.

ОПИСАНИЕ СЕКЦИИ:
{{ section.description }}

ТРЕБОВАНИЯ К СЕКЦИИ:
{% for rule in section.rules %}- {{ rule }}
{% endfor %}

ИСХОДНЫЕ ДОКУМЕНТЫ:
---
{{ source_text }}
---

Напиши текст секции «{{ section.title }}»:
""")

_VALIDATION_PROMPT_TEMPLATE = Template("""
Проверь текст секции «{{ section.title }}» на соответствие требованиям.

ТРЕБОВАНИЯ:
{% for rule in section.rules %}- {{ rule }}
{% endfor %}

ГЛОБАЛЬНЫЕ ТРЕБОВАНИЯ:
{% for rule in global_rules %}- {{ rule }}
{% endfor %}

ТЕКСТ ДЛЯ ПРОВЕРКИ:
---
{{ section_text }}
---

Верни результат проверки СТРОГО в формате JSON (без markdown, без пояснений):
{
  "errors": [
    {
      "type": "grammar|style|structure|missing_data|incorrect_data",
      "message": "описание ошибки",
      "recommendation": "как исправить",
      "severity": "error|warning|info"
    }
  ]
}
Если ошибок нет — верни {"errors": []}.
""")


# ─────────────────────────────────────────────────────────────────────────────
# Сервис
# ─────────────────────────────────────────────────────────────────────────────

class ReportGenerationService:

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def generate(
        self,
        template_schema: TemplateSchema,
        source_docs: list[ParsedDocument],
        params: dict[str, Any] | None = None,
    ) -> GenerationResult:
        """
        Главный метод: обходит секции шаблона, для каждой вызывает LLM,
        затем запускает нормоконтроль.
        """
        t0 = time.perf_counter()

        # Объединяем тексты всех источников
        source_text = self._build_source_text(source_docs)

        generated_sections: dict[str, str] = {}
        all_errors: list[ValidationErrorItem] = []

        total_prompt_tokens = 0
        total_completion_tokens = 0
        last_llm_result: LLMResult | None = None

        logger.info(
            "report_generation_start",
            template=template_schema.document_type,
            sections=len(template_schema.sections),
            source_docs=len(source_docs),
        )

        # ── Шаг 1: генерация секций ──────────────────────────────────────
        for section in template_schema.sections:
            section_text, llm_result = await self._generate_section(
                section=section,
                source_text=source_text,
            )
            generated_sections[section.id] = section_text
            last_llm_result = llm_result
            total_prompt_tokens += llm_result.prompt_tokens
            total_completion_tokens += llm_result.completion_tokens

            # Проверяем наличие маркера отсутствующих данных
            if "[ДАННЫЕ ОТСУТСТВУЮТ]" in section_text and section.required:
                all_errors.append(
                    ValidationErrorItem(
                        type="missing_data",
                        section_id=section.id,
                        message=f"В секции «{section.title}» отсутствуют необходимые данные",
                        recommendation=(
                            "Предоставьте исходные документы, содержащие информацию "
                            f"для секции «{section.title}»"
                        ),
                        severity="error",
                    )
                )

        # ── Шаг 2: нормоконтроль ─────────────────────────────────────────
        for section in template_schema.sections:
            section_text = generated_sections.get(section.id, "")
            if not section_text or "[ДАННЫЕ ОТСУТСТВУЮТ]" in section_text:
                continue  # нет смысла проверять пустую секцию

            validation_errors, llm_result = await self._validate_section(
                section=section,
                section_text=section_text,
                global_rules=template_schema.global_rules,
            )
            all_errors.extend(validation_errors)
            total_prompt_tokens += llm_result.prompt_tokens
            total_completion_tokens += llm_result.completion_tokens

        total_seconds = round(time.perf_counter() - t0, 2)

        logger.info(
            "report_generation_done",
            sections=len(generated_sections),
            errors=len(all_errors),
            total_seconds=total_seconds,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
        )

        # Финальный LLMResult — суммируем токены
        final_llm_result = LLMResult(
            content="",
            model=last_llm_result.model if last_llm_result else "",
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            latency_seconds=total_seconds,
        )

        return GenerationResult(
            sections=generated_sections,
            validation_errors=all_errors,
            llm_result=final_llm_result,
            total_seconds=total_seconds,
        )

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _build_source_text(self, docs: list[ParsedDocument]) -> str:
        """Объединяет все исходные документы в один текстовый блок."""
        parts: list[str] = []
        for doc in docs:
            if doc.error:
                parts.append(f"[ФАЙЛ: {doc.filename}]\n[ОШИБКА ЧТЕНИЯ: {doc.error}]")
                continue
            header = f"[ФАЙЛ: {doc.filename}]"
            # Ограничиваем размер одного документа (защита от переполнения контекста)
            text = doc.text[:40_000]
            if len(doc.text) > 40_000:
                text += "\n\n[... документ обрезан из-за размера ...]"
            parts.append(f"{header}\n{text}")

        return "\n\n{'─' * 60}\n\n".join(parts)

    async def _generate_section(
        self,
        section: TemplateSection,
        source_text: str,
    ) -> tuple[str, LLMResult]:
        user_prompt = _SECTION_PROMPT_TEMPLATE.render(
            section=section,
            source_text=source_text,
        )

        result = await self._llm.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        return result.content.strip(), result

    async def _validate_section(
        self,
        section: TemplateSection,
        section_text: str,
        global_rules: list[str],
    ) -> tuple[list[ValidationErrorItem], LLMResult]:
        user_prompt = _VALIDATION_PROMPT_TEMPLATE.render(
            section=section,
            section_text=section_text[:10_000],   # не отправляем огромные тексты
            global_rules=global_rules,
        )

        result = await self._llm.complete(
            system_prompt=(
                "Ты — эксперт нормоконтроля НТД. Проверяй строго. "
                "Отвечай ТОЛЬКО валидным JSON без markdown."
            ),
            user_prompt=user_prompt,
            temperature=0.0,  # детерминированно для валидации
        )

        errors: list[ValidationErrorItem] = []
        try:
            data = json.loads(result.content.strip())
            for e in data.get("errors", []):
                errors.append(
                    ValidationErrorItem(
                        type=e.get("type", "unknown"),
                        section_id=section.id,
                        message=e.get("message", ""),
                        recommendation=e.get("recommendation", ""),
                        severity=e.get("severity", "warning"),
                    )
                )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "validation_parse_error",
                section=section.id,
                error=str(exc),
            )

        return errors, result
