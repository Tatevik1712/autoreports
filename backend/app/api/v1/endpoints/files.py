"""
Эндпоинты загрузки исходных файлов.
"""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Pagination
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import SourceFile, SourceFileStatus
from app.schemas.schemas import MessageResponse, PaginatedResponse, SourceFileRead
from app.services.document.parser import get_document_parser
from app.services.storage import get_storage_client

router = APIRouter(prefix="/files", tags=["files"])
logger = get_logger(__name__)
settings = get_settings()


@router.post("", response_model=SourceFileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    current_user: CurrentUser,
    db: DbSession,
) -> SourceFile:
    """
    Загрузка исходного файла.
    Файл сохраняется в MinIO, текст извлекается сразу (парсинг).
    """
    # ── Валидация ────────────────────────────────────────────────────────────
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Неподдерживаемый формат файла: {ext}. "
                   f"Допустимые: {', '.join(settings.allowed_extensions)}",
        )

    content = await file.read()

    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл слишком большой. Максимум: {settings.max_upload_size_mb} МБ",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файл пустой",
        )

    # ── Определение MIME-типа ────────────────────────────────────────────────
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"

    # ── Загрузка в MinIO ─────────────────────────────────────────────────────
    storage = get_storage_client()
    storage_key = f"sources/{current_user.id}/{file.filename}"

    await storage.upload(
        bucket=storage.bucket_sources,
        key=storage_key,
        content=content,
        content_type=content_type,
    )

    # ── Парсинг (сразу, чтобы не делать при генерации) ───────────────────────
    parser = get_document_parser()
    parsed = await parser.parse(content, file.filename or "", content_type)

    # ── Сохранение в БД ──────────────────────────────────────────────────────
    source_file = SourceFile(
        owner_id=current_user.id,
        original_filename=file.filename or "unknown",
        content_type=content_type,
        size_bytes=len(content),
        storage_key=storage_key,
        status=SourceFileStatus.parse_error if parsed.error else SourceFileStatus.parsed,
        parse_error=parsed.error,
        extracted_text=parsed.text[:100_000] if parsed.text else None,  # ограничиваем в БД
        meta=parsed.meta,
    )
    db.add(source_file)
    await db.commit()
    await db.refresh(source_file)

    if parsed.error:
        logger.warning("file_parse_error", file_id=source_file.id, error=parsed.error)
    else:
        logger.info("file_uploaded", file_id=source_file.id, filename=file.filename, chars=len(parsed.text))

    return source_file


@router.get("", response_model=PaginatedResponse)
async def list_files(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> PaginatedResponse:
    """Список файлов текущего пользователя."""
    from sqlalchemy import func
    total_result = await db.execute(
        select(func.count()).select_from(SourceFile).where(
            SourceFile.owner_id == current_user.id
        )
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(SourceFile)
        .where(SourceFile.owner_id == current_user.id)
        .order_by(SourceFile.uploaded_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    files = result.scalars().all()

    return PaginatedResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=[SourceFileRead.model_validate(f) for f in files],
    )


@router.get("/{file_id}", response_model=SourceFileRead)
async def get_file(
    file_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> SourceFile:
    """Метаданные файла."""
    sf = await db.get(SourceFile, file_id)
    if not sf or sf.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return sf


@router.delete("/{file_id}", response_model=MessageResponse)
async def delete_file(
    file_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Удаление файла."""
    sf = await db.get(SourceFile, file_id)
    if not sf or sf.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Файл не найден")

    storage = get_storage_client()
    try:
        await storage.delete(bucket=storage.bucket_sources, key=sf.storage_key)
    except Exception as exc:
        logger.warning("file_storage_delete_error", file_id=file_id, error=str(exc))

    await db.delete(sf)
    await db.commit()

    return MessageResponse(message="Файл удалён")
