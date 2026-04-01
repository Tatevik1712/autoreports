"""
Эндпоинты шаблонов отчётов.
v2: возвращает document_type, sections с key-алиасами, rules для frontend.
"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentAdmin, CurrentUser, DbSession, Pagination
from app.core.logging import get_logger
from app.models.models import AuditLog, ReportTemplate
from app.schemas.schemas import (
    MessageResponse, PaginatedResponse,
    TemplateCreate, TemplateList, TemplateRead,
)

router = APIRouter(prefix="/templates", tags=["templates"])
logger = get_logger(__name__)


@router.get("", response_model=PaginatedResponse)
async def list_templates(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> PaginatedResponse:
    total_result = await db.execute(
        select(func.count()).select_from(ReportTemplate).where(ReportTemplate.is_active == True)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(ReportTemplate)
        .where(ReportTemplate.is_active == True)
        .order_by(ReportTemplate.name, ReportTemplate.version.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    templates = result.scalars().all()

    return PaginatedResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=[TemplateList.from_orm_with_schema(t).model_dump() for t in templates],
    )


@router.get("/{template_id}", response_model=TemplateRead)
async def get_template(
    template_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    template = await db.get(ReportTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return TemplateRead.from_orm_with_schema(template).model_dump()


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    current_admin: CurrentAdmin,
    db: DbSession,
) -> dict:
    version_result = await db.execute(
        select(func.max(ReportTemplate.version)).where(ReportTemplate.slug == payload.slug)
    )
    latest_version = version_result.scalar_one() or 0
    new_version = latest_version + 1

    template = ReportTemplate(
        slug=payload.slug,
        version=new_version,
        name=payload.name,
        description=payload.description,
        schema=payload.schema.model_dump(),
        created_by_id=current_admin.id,
    )
    db.add(template)
    db.add(AuditLog(
        user_id=current_admin.id,
        action="template_create",
        resource_type="template",
        extra={"slug": payload.slug, "version": new_version},
    ))
    await db.commit()
    await db.refresh(template)

    logger.info("template_created", slug=payload.slug, version=new_version)
    return TemplateRead.from_orm_with_schema(template).model_dump()


@router.put("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: str,
    payload: TemplateCreate,
    current_admin: CurrentAdmin,
    db: DbSession,
) -> dict:
    old = await db.get(ReportTemplate, template_id)
    if not old:
        raise HTTPException(status_code=404, detail="Шаблон не найден")

    old.is_active = False

    new_template = ReportTemplate(
        slug=old.slug,
        version=old.version + 1,
        name=payload.name,
        description=payload.description,
        schema=payload.schema.model_dump(),
        created_by_id=current_admin.id,
    )
    db.add(new_template)
    db.add(AuditLog(
        user_id=current_admin.id,
        action="template_update",
        resource_type="template",
        resource_id=template_id,
        extra={"old_version": old.version, "new_version": new_template.version},
    ))
    await db.commit()
    await db.refresh(new_template)

    logger.info("template_updated", slug=old.slug, new_v=new_template.version)
    return TemplateRead.from_orm_with_schema(new_template).model_dump()


@router.delete("/{template_id}", response_model=MessageResponse)
async def deactivate_template(
    template_id: str,
    current_admin: CurrentAdmin,
    db: DbSession,
) -> MessageResponse:
    template = await db.get(ReportTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")

    template.is_active = False
    db.add(AuditLog(
        user_id=current_admin.id,
        action="template_deactivate",
        resource_type="template",
        resource_id=template_id,
    ))
    await db.commit()
    return MessageResponse(message=f"Шаблон «{template.name}» деактивирован")
