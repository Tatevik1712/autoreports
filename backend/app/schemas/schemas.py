"""
Pydantic v2 схемы — валидация запросов и сериализация ответов.
Версия 2: поля приведены в соответствие с frontend types/index.ts
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.models import ReportStatus, SourceFileStatus, UserRole


class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)



# Auth
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


# User
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


# Template
class TemplateSection(BaseModel):
    """Секция шаблона.
    Поле 'id' используется в backend-логике (RAG, генерация).
    Поле 'key' — алиас для frontend-совместимости.
    """
    id: str
    title: str
    description: str = ""
    required: bool = True
    rules: list[str] = Field(default_factory=list)
    fields: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def key(self) -> str:
        """Алиас id для frontend-совместимости."""
        return self.id


class TemplateSchema(BaseModel):
    """Машиночитаемая схема шаблона отчёта."""
    document_type: str
    sections: list[TemplateSection]
    global_rules: list[str] = Field(default_factory=list)
    output_format: str = "docx"


class TemplateCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9\-]+$")
    name: str = Field(max_length=255)
    description: str = ""
    schema: TemplateSchema


class TemplateList(OrmBase):
    """Список шаблонов.
    Добавлено поле document_type — берётся из schema.document_type.
    """
    id: str
    slug: str
    version: int
    name: str
    description: str
    is_active: bool
    created_at: datetime

    # Вычисляемое поле — извлекается из schema при сериализации
    document_type: str = ""

    @classmethod
    def from_orm_with_schema(cls, obj) -> "TemplateList":
        """Создаёт TemplateList с document_type из schema."""
        instance = cls.model_validate(obj)
        if hasattr(obj, 'schema') and isinstance(obj.schema, dict):
            instance.document_type = obj.schema.get("document_type", "")
        return instance


class TemplateRead(OrmBase):
    """Детальный вид шаблона.
    Добавлены поля для frontend-совместимости:
    - document_type (из schema)
    - sections (из schema.sections с key-алиасом)
    - rules (из schema.global_rules)
    """
    id: str
    slug: str
    version: int
    name: str
    description: str
    is_active: bool
    schema: dict
    created_at: datetime
    updated_at: datetime

    # Поля, вычисляемые из schema для frontend
    document_type: str = ""
    sections: list[dict] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)

    @classmethod
    def from_orm_with_schema(cls, obj) -> "TemplateRead":
        instance = cls.model_validate(obj)
        if hasattr(obj, 'schema') and isinstance(obj.schema, dict):
            schema = obj.schema
            instance.document_type = schema.get("document_type", "")
            instance.rules = schema.get("global_rules", [])
            # sections: добавляем key как алиас id для frontend
            raw_sections = schema.get("sections", [])
            instance.sections = [
                {**s, "key": s.get("id", "")} for s in raw_sections
            ]
        return instance


# ─────────────────────────────────────────────────────────────────────────────
# SourceFile
# ─────────────────────────────────────────────────────────────────────────────

class SourceFileRead(OrmBase):
    """Файл-источник.
    Добавлены алиасы для frontend-совместимости:
    - filename (= original_filename)
    - size (= size_bytes)
    - error_message (= parse_error)
    """
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    status: SourceFileStatus
    parse_error: str | None
    meta: dict
    uploaded_at: datetime

    # Алиасы для frontend
    @property
    def filename(self) -> str:
        return self.original_filename

    @property
    def size(self) -> int:
        return self.size_bytes

    @property
    def error_message(self) -> str | None:
        return self.parse_error

    model_config = ConfigDict(
        from_attributes=True,
        # Включаем сериализацию computed fields через populate_by_name
        populate_by_name=True,
    )

    def model_post_init(self, __context: Any) -> None:
        """Ничего — алиасы через @property."""
        pass

    def model_dump(self, **kwargs) -> dict:
        """Переопределяем чтобы включить алиасы в JSON-ответ."""
        data = super().model_dump(**kwargs)
        data["filename"] = self.original_filename
        data["size"] = self.size_bytes
        data["error_message"] = self.parse_error
        return data

    def model_dump_json(self, **kwargs) -> str:
        import json
        return json.dumps(self.model_dump(**kwargs))


# ─────────────────────────────────────────────────────────────────────────────
# ValidationError
# ─────────────────────────────────────────────────────────────────────────────

class ValidationErrorItem(BaseModel):
    """Одна ошибка нормоконтроля.
    Поля совпадают с frontend ValidationError.
    """
    type: str
    section_id: str | None = None
    field_id: str | None = None
    message: str
    recommendation: str
    severity: str = "warning"

    def model_dump(self, **kwargs) -> dict:
        """Добавляем section как алиас section_id для frontend."""
        data = super().model_dump(**kwargs)
        data["section"] = self.section_id  # frontend ждёт "section"
        return data


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    title: str = Field(max_length=500)
    template_id: str
    source_file_ids: list[str] = Field(min_length=1)
    generation_params: dict[str, Any] = Field(default_factory=dict)


class ReportRegenerate(BaseModel):
    generation_params: dict[str, Any] = Field(default_factory=dict)


class ReportRead(OrmBase):
    """Список отчётов.
    Добавлены поля для frontend-совместимости:
    - template_name (из связи template)
    - username (из связи owner)
    - source_file_ids (список id файлов)
    - processing_time_seconds (алиас processing_seconds)
    """
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

    # Алиасы для frontend
    template_name: str | None = None
    username: str | None = None
    user_id: str | None = None
    source_file_ids: list[str] = Field(default_factory=list)
    processing_time_seconds: float | None = None
    template_id: str | None = None

    @classmethod
    def from_orm_report(cls, report) -> "ReportRead":
        """Создаёт ReportRead с заполненными алиасными полями."""
        instance = cls.model_validate(report)
        # Подтягиваем данные из связей если они загружены
        if hasattr(report, 'template') and report.template:
            instance.template_name = report.template.name
            instance.template_id = report.template.id
        if hasattr(report, 'owner') and report.owner:
            instance.username = report.owner.username
            instance.user_id = report.owner.id
        if hasattr(report, 'source_files') and report.source_files:
            instance.source_file_ids = [rsf.source_file_id for rsf in report.source_files]
        # Алиас для processing_seconds
        instance.processing_time_seconds = report.processing_seconds
        return instance


class ReportDetail(ReportRead):
    """Детальный вид отчёта с файлами и RAG debug."""
    owner: UserRead | None = None
    template: TemplateList | None = None
    source_files: list[SourceFileRead] = []
    rag_debug: dict | None = None

    @classmethod
    def from_orm_report(cls, report) -> "ReportDetail":
        # Сначала вручную собираем source_files из M2M-связи
        source_files_data = []
        if hasattr(report, 'source_files') and report.source_files:
            for rsf in report.source_files:
                sf = rsf.source_file if hasattr(rsf, 'source_file') else None
                if sf:
                    source_files_data.append({
                        "id": sf.id,
                        "original_filename": sf.original_filename,
                        "filename": sf.original_filename,
                        "content_type": sf.content_type,
                        "size_bytes": sf.size_bytes,
                        "size": sf.size_bytes,
                        "status": sf.status,
                        "parse_error": sf.parse_error,
                        "error_message": sf.parse_error,
                        "meta": sf.meta or {},
                        "uploaded_at": sf.uploaded_at,
                        "user_id": sf.owner_id,
                    })

        # Создаём instance без source_files
        instance = cls.model_validate(report, context={"source_files": []})
        instance.source_files = []

        # Заполняем алиасные поля
        if hasattr(report, 'template') and report.template:
            instance.template_name = report.template.name
            instance.template_id = report.template.id
        if hasattr(report, 'owner') and report.owner:
            instance.username = report.owner.username
            instance.user_id = report.owner.id
        if hasattr(report, 'source_files') and report.source_files:
            instance.source_file_ids = [rsf.source_file_id for rsf in report.source_files]
        instance.processing_time_seconds = report.processing_seconds

        # RAG debug
        params = getattr(report, 'generation_params', {}) or {}
        rag_stats = params.get("_rag_stats", {})
        retrieval_debug = params.get("_retrieval_debug", [])
        if rag_stats:
            instance.rag_debug = {
                "total_chunks": rag_stats.get("total_chunks", 0),
                "total_tables": rag_stats.get("table_chunks", 0),
                "total_numeric_blocks": rag_stats.get("numeric_chunks", 0),
                "document_map": rag_stats.get("document_map", ""),
                "indexing_errors": rag_stats.get("errors", []),
                "chunks": [
                    {
                        "query": chunk.get("query", ""),
                        "score": chunk.get("rerank", chunk.get("rrf", 0)),
                        "preview": chunk.get("preview", ""),
                        "section": chunk.get("section", ""),
                    }
                    for section_debug in retrieval_debug
                    for chunk in section_debug.get("chunks", [])
                ][:20],
            }

        return instance

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
