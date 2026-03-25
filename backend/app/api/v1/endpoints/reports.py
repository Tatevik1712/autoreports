"""
Эндпоинты отчётов: создание, статус, скачивание, перегенерация.
"""
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentAdmin, CurrentUser, DbSession, Pagination
from app.core.logging import get_logger
from app.models.models import (
    AuditLog, Report, ReportSourceFile, ReportStatus,
    ReportTemplate, SourceFile, UserRole,
)
from app.schemas.schemas import (
    MessageResponse, PaginatedResponse,
    ReportCreate, ReportDetail, ReportRead, ReportRegenerate,
)
from app.services.storage import get_storage_client
from app.workers.tasks import process_report

router = APIRouter(prefix="/reports", tags=["reports"])
logger = get_logger(__name__)


@router.post("", response_model=ReportRead, status_code=status.HTTP_202_ACCEPTED)
async def create_report(
    payload: ReportCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> Report:
    """
    Создаёт отчёт и ставит задачу в очередь Celery.
    Возвращает сразу (статус pending) — результат асинхронный.
    """
    # Проверяем шаблон
    template = await db.get(ReportTemplate, payload.template_id)
    if not template or not template.is_active:
        raise HTTPException(status_code=404, detail="Шаблон не найден или неактивен")

    # Проверяем файлы — только свои
    file_results = await db.execute(
        select(SourceFile).where(
            SourceFile.id.in_(payload.source_file_ids),
            SourceFile.owner_id == current_user.id,
        )
    )
    files = file_results.scalars().all()

    if len(files) != len(payload.source_file_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Один или несколько файлов не найдены",
        )

    # Создаём отчёт
    report = Report(
        owner_id=current_user.id,
        template_id=template.id,
        title=payload.title,
        generation_params=payload.generation_params,
        template_version=template.version,
    )
    db.add(report)
    await db.flush()  # получаем report.id

    # Привязываем файлы
    for sf in files:
        db.add(ReportSourceFile(report_id=report.id, source_file_id=sf.id))

    db.add(AuditLog(
        user_id=current_user.id,
        action="report_create",
        resource_type="report",
        resource_id=report.id,
        extra={"template": template.slug, "files": len(files)},
    ))

    await db.commit()
    await db.refresh(report)

    # Ставим задачу в очередь (Celery)
    task = process_report.apply_async(args=[report.id], queue="reports")
    report.task_id = task.id
    await db.commit()

    logger.info("report_queued", report_id=report.id, task_id=task.id, user=current_user.id)
    return report


@router.get("", response_model=PaginatedResponse)
async def list_reports(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> PaginatedResponse:
    """
    Список отчётов.
    Пользователь видит только свои. Администратор — все.
    """
    base_query = select(Report)
    count_query = select(func.count()).select_from(Report)

    if current_user.role != UserRole.admin:
        base_query = base_query.where(Report.owner_id == current_user.id)
        count_query = count_query.where(Report.owner_id == current_user.id)

    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(
        base_query
        .order_by(Report.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    reports = result.scalars().all()

    return PaginatedResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=[ReportRead.model_validate(r) for r in reports],
    )


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> Report:
    """Детальный вид отчёта с файлами и шаблоном."""
    result = await db.execute(
        select(Report)
        .where(Report.id == report_id)
        .options(
            selectinload(Report.owner),
            selectinload(Report.template),
            selectinload(Report.source_files).selectinload(ReportSourceFile.source_file),
        )
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    # Пользователь видит только свои
    if current_user.role != UserRole.admin and report.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    return report


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    """Скачивание готового DOCX-отчёта."""
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    if current_user.role != UserRole.admin and report.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    if report.status != ReportStatus.done:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Отчёт ещё не готов. Текущий статус: {report.status.value}",
        )

    if not report.result_storage_key:
        raise HTTPException(status_code=404, detail="Файл отчёта не найден")

    storage = get_storage_client()
    content = await storage.download(
        bucket=storage.bucket_reports,
        key=report.result_storage_key,
    )

    safe_title = "".join(c for c in report.title if c.isalnum() or c in " _-")[:50]
    filename = f"{safe_title}.docx"

    db.add(AuditLog(
        user_id=current_user.id,
        action="report_download",
        resource_type="report",
        resource_id=report_id,
    ))
    await db.commit()

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{report_id}/regenerate", response_model=ReportRead, status_code=status.HTTP_202_ACCEPTED)
async def regenerate_report(
    report_id: str,
    payload: ReportRegenerate,
    current_user: CurrentUser,
    db: DbSession,
) -> Report:
    """
    Перегенерация отчёта с новыми настройками.
    Файлы не нужно загружать повторно.
    """
    original = await db.get(Report, report_id)
    if not original:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    if current_user.role != UserRole.admin and original.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    # Клонируем с новыми параметрами
    new_report = Report(
        owner_id=original.owner_id,
        template_id=original.template_id,
        title=f"{original.title} [перегенерация]",
        generation_params={**original.generation_params, **payload.generation_params},
        template_version=original.template_version,
    )
    db.add(new_report)
    await db.flush()

    # Копируем ссылки на файлы
    for rsf in original.source_files:
        db.add(ReportSourceFile(
            report_id=new_report.id,
            source_file_id=rsf.source_file_id,
        ))

    await db.commit()
    await db.refresh(new_report)

    task = process_report.apply_async(args=[new_report.id], queue="reports")
    new_report.task_id = task.id
    await db.commit()

    logger.info("report_regenerated", original=report_id, new=new_report.id)
    return new_report


@router.delete("/{report_id}", response_model=MessageResponse)
async def delete_report(
    report_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Удаление отчёта (и файла из MinIO)."""
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    if current_user.role != UserRole.admin and report.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    # Удаляем файл из хранилища
    if report.result_storage_key:
        storage = get_storage_client()
        try:
            await storage.delete(bucket=storage.bucket_reports, key=report.result_storage_key)
        except Exception as exc:
            logger.warning("report_storage_delete_error", report_id=report_id, error=str(exc))

    await db.delete(report)
    await db.commit()

    return MessageResponse(message="Отчёт удалён")
