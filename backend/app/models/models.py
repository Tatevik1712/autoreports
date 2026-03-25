"""
SQLAlchemy ORM модели.
Все таблицы проекта в одном файле — удобно для alembic autogenerate.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class ReportStatus(str, enum.Enum):
    pending = "pending"         # ждёт в очереди
    processing = "processing"   # обрабатывается
    done = "done"               # готов
    error = "error"             # ошибка обработки


class SourceFileStatus(str, enum.Enum):
    uploaded = "uploaded"
    parsed = "parsed"
    parse_error = "parse_error"


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.user, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # relations
    reports: Mapped[list["Report"]] = relationship(back_populates="owner", lazy="select")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user", lazy="select")


# ─────────────────────────────────────────────────────────────────────────────
# ReportTemplate
# ─────────────────────────────────────────────────────────────────────────────

class ReportTemplate(Base):
    __tablename__ = "report_templates"
    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_template_slug_version"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # JSON-схема шаблона — секции, поля, правила
    schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_by_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    created_by: Mapped["User"] = relationship(lazy="select")
    reports: Mapped[list["Report"]] = relationship(back_populates="template", lazy="select")


# ─────────────────────────────────────────────────────────────────────────────
# SourceFile — загруженный пользователем файл
# ─────────────────────────────────────────────────────────────────────────────

class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # путь в MinIO
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[SourceFileStatus] = mapped_column(
        Enum(SourceFileStatus), default=SourceFileStatus.uploaded, nullable=False
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # извлечённый текст (для быстрого доступа без LLM)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # метаданные: кол-во страниц, таблиц и т.д.
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    owner: Mapped["User"] = relationship(lazy="select")


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True
    )
    template_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("report_templates.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus), default=ReportStatus.pending, nullable=False, index=True
    )

    # ID Celery-задачи (для опроса статуса)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # путь к итоговому файлу в MinIO
    result_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Параметры генерации (для перегенерации) ──────────────────────────
    generation_params: Mapped[dict] = mapped_column(JSONB, default=dict)

    # ── Аудит LLM ────────────────────────────────────────────────────────
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Ошибки ───────────────────────────────────────────────────────────
    # список ошибок нормоконтроля (сохраняется даже при status=done)
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    owner: Mapped["User"] = relationship(back_populates="reports", lazy="select")
    template: Mapped["ReportTemplate"] = relationship(back_populates="reports", lazy="select")
    source_files: Mapped[list["ReportSourceFile"]] = relationship(
        back_populates="report", lazy="select", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ReportSourceFile — M2M: отчёт ↔ исходные файлы
# ─────────────────────────────────────────────────────────────────────────────

class ReportSourceFile(Base):
    __tablename__ = "report_source_files"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("reports.id"), nullable=False
    )
    source_file_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("source_files.id"), nullable=False
    )

    report: Mapped["Report"] = relationship(back_populates="source_files", lazy="select")
    source_file: Mapped["SourceFile"] = relationship(lazy="select")


# ─────────────────────────────────────────────────────────────────────────────
# AuditLog — действия пользователей
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # IP и User-Agent — без чувствительных данных
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Дополнительный контекст (без паролей/токенов — см. logging.py)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    user: Mapped["User | None"] = relationship(back_populates="audit_logs", lazy="select")
