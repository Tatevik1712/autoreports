"""
Задача обработки отчёта — v2 с RAG pipeline.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from celery.utils.log import get_task_logger
from app.workers.celery_app import celery_app
import asyncio

logger = get_task_logger(__name__)

# Получаем текущий event loop или создаем новый
def _run_async(coro):
    """Запускает корутину в существующем event loop или создает новый"""
    try:
        # Пытаемся получить текущий running loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Нет running loop, создаем новый
        return asyncio.run(coro)
    else:
        # Есть running loop, используем create_task
        return loop.create_task(coro)

@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_report",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=900,
    time_limit=960,
)
def process_report(self, report_id: str) -> dict:
    logger.info(f"[task] Starting report {report_id}, task={self.request.id}")
    try:
        result = _run_async(_process_report_async(report_id))
        logger.info(f"[task] Done report {report_id}: {result}")
        return result
    except Exception as exc:
        logger.error(f"[task] Failed report {report_id}: {exc}", exc_info=True)
        _run_async(_mark_report_error(report_id, str(exc)))
        raise self.retry(exc=exc)


async def _process_report_async(report_id: str) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db.session import AsyncSessionLocal
    from app.models.models import Report, ReportSourceFile, ReportStatus
    from app.services.document.parser import get_document_parser
    from app.services.llm.provider import get_llm_provider
    from app.services.report.rag_generator import get_rag_report_generator
    from app.services.report.assembler import get_docx_assembler
    from app.services.storage import get_storage_client
    from app.schemas.schemas import TemplateSchema

    async with AsyncSessionLocal() as db:
        # BUG FIX: db.refresh() не принимает список атрибутов в asyncpg.
        # Используем selectinload через явный select-запрос.
        result = await db.execute(
            select(Report)
            .where(Report.id == report_id)
            .options(
                selectinload(Report.template),
                selectinload(Report.source_files).selectinload(ReportSourceFile.source_file),
            )
        )
        report = result.scalar_one_or_none()
        if not report:
            raise ValueError(f"Report {report_id} not found")

        report.status = ReportStatus.processing
        await db.commit()

        storage = get_storage_client()
        parser = get_document_parser()
        parsed_docs = []

        for rsf in report.source_files:
            sf = rsf.source_file
            try:
                content = await storage.download(
                    bucket=storage.bucket_sources,
                    key=sf.storage_key,
                )
                parsed = await parser.parse(content, sf.original_filename, sf.content_type)
                parsed_docs.append(parsed)
                logger.info(f"Parsed {sf.original_filename}: {len(parsed.text)} chars")
            except Exception as exc:
                logger.error(f"Parse failed: {sf.original_filename}: {exc}")
                from app.services.document.parser import ParsedDocument
                parsed_docs.append(ParsedDocument(
                    filename=sf.original_filename,
                    content_type=sf.content_type,
                    text="",
                    error=str(exc),
                ))

        template_schema = TemplateSchema(**report.template.schema)
        llm = get_llm_provider()
        generator = get_rag_report_generator(llm=llm, report_id=report_id)

        gen_result = await generator.generate(
            template_schema=template_schema,
            source_docs=parsed_docs,
            params=report.generation_params,
        )

        assembler = get_docx_assembler()
        docx_bytes = assembler.build(
            template_schema=template_schema,
            sections=gen_result.sections,
            validation_errors=gen_result.validation_errors,
            report_title=report.title,
        )

        result_key = f"reports/{report_id}/result.docx"
        await storage.upload(
            bucket=storage.bucket_reports,
            key=result_key,
            content=docx_bytes,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )

        report.status = ReportStatus.done
        report.result_storage_key = result_key
        report.completed_at = datetime.now(timezone.utc)
        report.llm_model = gen_result.llm_result.model
        report.template_version = report.template.version
        report.processing_seconds = gen_result.total_seconds
        report.prompt_tokens = gen_result.llm_result.prompt_tokens
        report.completion_tokens = gen_result.llm_result.completion_tokens
        report.validation_errors = [e.model_dump() for e in gen_result.validation_errors]
        report.generation_params = {
            **report.generation_params,
            "_rag_stats": gen_result.indexing_stats,
            "_retrieval_debug": gen_result.retrieval_debug,
        }
        await db.commit()

        return {
            "report_id": report_id,
            "status": "done",
            "validation_errors": len(gen_result.validation_errors),
            "total_chunks": gen_result.indexing_stats.get("total_chunks", 0),
            "seconds": gen_result.total_seconds,
        }


async def _mark_report_error(report_id: str, error_message: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models.models import Report, ReportStatus

    async with AsyncSessionLocal() as db:
        report = await db.get(Report, report_id)
        if report:
            report.status = ReportStatus.error
            report.error_message = error_message[:2000]
            report.completed_at = datetime.now(timezone.utc)
            await db.commit()
