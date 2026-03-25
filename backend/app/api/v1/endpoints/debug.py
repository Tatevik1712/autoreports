"""
Эндпоинт диагностики RAG — показывает какие чанки попали в промпт.
Только для администраторов.
"""
from fastapi import APIRouter, HTTPException
from app.api.deps import CurrentAdmin, DbSession

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/reports/{report_id}/retrieval")
async def get_retrieval_debug(
    report_id: str,
    current_admin: CurrentAdmin,
    db: DbSession,
) -> dict:
    """
    Возвращает статистику RAG-индексации и нормоконтроля для отчёта.
    Показывает: сколько чанков, таблиц, какие ошибки индексации.
    """
    report = await db.get(__import__("app.models.models", fromlist=["Report"]).Report, report_id)
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
