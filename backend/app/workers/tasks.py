"""
Задача обработки отчёта.
Весь pipeline: скачать файлы → распарсить → сгенерировать → собрать DOCX → загрузить.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


def _run_async(coro):
    """Запуск корутины из синхронного контекста Celery."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_report",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=600,   # 10 минут
    time_limit=660,
)
def process_report(self, report_id: str) -> dict:
    """
    Celery-задача генерации отчёта.
    Все тяжёлые операции делегируются в async pipeline.
    """
    logger.info(f"[task] Starting report {report_id}")
    try:
        result = _run_async(_process_report_async(report_id, self.request.id))
        logger.info(f"[task] Done report {report_id}")
        return result
    except Exception as exc:
        logger.error(f"[task] Failed report {report_id}: {exc}")
        _run_async(_mark_report_error(report_id, str(exc)))
        raise self.retry(exc=exc)


async def _process_report_async(report_id: str, task_id: str) -> dict:
    """
    Асинхронный pipeline обработки отчёта.
    Импорты внутри функции, чтобы не тянуть всё при старте воркера.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.models import Report, ReportStatus, SourceFile
    from app.services.document.parser import get_document_parser
    from app.services.llm.provider import get_llm_provider
    from app.services.report.generator import ReportGenerationService
    from app.services.report.assembler import get_docx_assembler
    from app.services.storage import get_storage_client
    from app.schemas.schemas import TemplateSchema

    async with AsyncSessionLocal() as db:
        # ── 1. Загружаем отчёт из БД ──────────────────────────────────
        report = await db.get(Report, report_id)
        if not report:
            raise ValueError(f"Report {report_id} not found")

        report.status = ReportStatus.processing
        await db.flush()

        # ── 2. Скачиваем исходные файлы из MinIO ──────────────────────
        storage = get_storage_client()
        parser = get_document_parser()
        parsed_docs = []

        for rsf in report.source_files:
            sf: SourceFile = rsf.source_file
            try:
                content = await storage.download(
                    bucket=storage.bucket_sources,
                    key=sf.storage_key,
                )
                parsed = await parser.parse(content, sf.original_filename, sf.content_type)
                parsed_docs.append(parsed)
                logger.info(f"Parsed {sf.original_filename}: {len(parsed.text)} chars")
            except Exception as exc:
                logger.error(f"Failed to parse {sf.original_filename}: {exc}")
                from app.services.document.parser import ParsedDocument
                parsed_docs.append(ParsedDocument(
                    filename=sf.original_filename,
                    content_type=sf.content_type,
                    text="",
                    error=str(exc),
                ))

        # ── 3. Генерация ───────────────────────────────────────────────
        template_schema = TemplateSchema(**report.template.schema)
        llm = get_llm_provider()
        generator = ReportGenerationService(llm)

        gen_result = await generator.generate(
            template_schema=template_schema,
            source_docs=parsed_docs,
            params=report.generation_params,
        )

        # ── 4. Сборка DOCX ────────────────────────────────────────────
        assembler = get_docx_assembler()
        docx_bytes = assembler.build(
            template_schema=template_schema,
            sections=gen_result.sections,
            validation_errors=gen_result.validation_errors,
            report_title=report.title,
        )

        # ── 5. Загрузка результата в MinIO ────────────────────────────
        result_key = f"reports/{report_id}/result.docx"
        await storage.upload(
            bucket=storage.bucket_reports,
            key=result_key,
            content=docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        # ── 6. Обновляем запись в БД ──────────────────────────────────
        report.status = ReportStatus.done
        report.result_storage_key = result_key
        report.completed_at = datetime.now(timezone.utc)
        report.llm_model = gen_result.llm_result.model
        report.template_version = report.template.version
        report.processing_seconds = gen_result.total_seconds
        report.prompt_tokens = gen_result.llm_result.prompt_tokens
        report.completion_tokens = gen_result.llm_result.completion_tokens
        report.validation_errors = [e.model_dump() for e in gen_result.validation_errors]

        await db.commit()

        return {
            "report_id": report_id,
            "status": "done",
            "errors": len(gen_result.validation_errors),
            "seconds": gen_result.total_seconds,
        }


async def _mark_report_error(report_id: str, error_message: str) -> None:
    """Помечаем отчёт как ошибочный в БД."""
    from app.db.session import AsyncSessionLocal
    from app.models.models import Report, ReportStatus

    async with AsyncSessionLocal() as db:
        report = await db.get(Report, report_id)
        if report:
            report.status = ReportStatus.error
            report.error_message = error_message[:2000]
            report.completed_at = datetime.now(timezone.utc)
            await db.commit()
