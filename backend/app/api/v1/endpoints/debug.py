"""
Эндпоинт диагностики RAG.
FIX: заменён __import__ антипаттерн на нормальный импорт.
Только для администраторов.
"""
from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentAdmin, DbSession
from app.models.models import Report  # FIX: нормальный импорт

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/reports/{report_id}/retrieval")
async def get_retrieval_debug(
    report_id: str,
    current_admin: CurrentAdmin,
    db: DbSession,
) -> dict:
    """Статистика RAG для отчёта — только для администраторов."""
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    rag_stats = report.generation_params.get("_rag_stats", {})

    return {
        "report_id":         report_id,
        "report_title":      report.title,
        "llm_model":         report.llm_model,
        "processing_sec":    report.processing_seconds,
        "prompt_tokens":     report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "indexing": {
            "total_docs":     rag_stats.get("total_docs"),
            "indexed_docs":   rag_stats.get("indexed_docs"),
            "total_chunks":   rag_stats.get("total_chunks"),
            "table_chunks":   rag_stats.get("table_chunks"),
            "numeric_chunks": rag_stats.get("numeric_chunks"),
            "errors":         rag_stats.get("errors", []),
        },
        "document_map":      rag_stats.get("document_map", ""),
        "validation_errors": report.validation_errors,
        "retrieval_debug":   report.generation_params.get("_retrieval_debug", []),
    }
