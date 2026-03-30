"""
Pydantic v2 схемы — валидация запросов и сериализация ответов.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.models import ReportStatus, SourceFileStatus, UserRole


# ─────────────────────────────────────────────────────────────────────────────
# Base helpers
# ─────────────────────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)


class UserRead(OrmBase):
    id: str
    email: str
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    is_active: bool | None = None
    role: UserRole | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Template
# ─────────────────────────────────────────────────────────────────────────────

class TemplateSection(BaseModel):
    """Секция шаблона — например «Аннотация», «Введение», «Методика»."""
    id: str
    title: str
    description: str = ""
    required: bool = True
    # Правила нормоконтроля для этой секции
    rules: list[str] = Field(default_factory=list)
    # Поля внутри секции
    fields: list[dict[str, Any]] = Field(default_factory=list)


class TemplateSchema(BaseModel):
    """Машиночитаемая схема шаблона отчёта."""
    document_type: str          # "НИР", "ОКР", "Аналитическая записка" и т.д.
    sections: list[TemplateSection]
    global_rules: list[str] = Field(default_factory=list)
    output_format: str = "docx"


class TemplateCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9\-]+$")
    name: str = Field(max_length=255)
    description: str = ""
    schema: TemplateSchema


class TemplateRead(OrmBase):
    id: str
    slug: str
    version: int
    name: str
    description: str
    is_active: bool
    schema: dict
    created_at: datetime
    updated_at: datetime


class TemplateList(OrmBase):
    id: str
    slug: str
    version: int
    name: str
    description: str
    is_active: bool
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# SourceFile
# ─────────────────────────────────────────────────────────────────────────────

class SourceFileRead(OrmBase):
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    status: SourceFileStatus
    parse_error: str | None
    meta: dict
    uploaded_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# ValidationError (результат нормоконтроля)
# ─────────────────────────────────────────────────────────────────────────────

class ValidationErrorItem(BaseModel):
    """Одна ошибка нормоконтроля."""
    type: str       # "missing_data" | "grammar" | "style" | "structure" | "incorrect_data"
    section_id: str | None = None
    field_id: str | None = None
    message: str
    recommendation: str
    severity: str = "warning"   # "error" | "warning" | "info"


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    title: str = Field(max_length=500)
    template_id: str
    source_file_ids: list[str] = Field(min_length=1)
    generation_params: dict[str, Any] = Field(default_factory=dict)


class ReportRegenerate(BaseModel):
    """Перегенерация без повторной загрузки файлов."""
    generation_params: dict[str, Any] = Field(default_factory=dict)


class ReportRead(OrmBase):
    id: str
    title: str
    status: ReportStatus
    task_id: str | None
    llm_model: str | None
    template_version: int | None
    processing_seconds: float | None
    validation_errors: list
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class ReportDetail(ReportRead):
    """Детальный вид — включает ссылки на файлы."""
    owner: UserRead
    template: TemplateList
    source_files: list[SourceFileRead] = []


# ─────────────────────────────────────────────────────────────────────────────
# Generic responses
# ─────────────────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]
