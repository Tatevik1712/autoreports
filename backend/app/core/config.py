from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────────
    app_name: str = "AutoReports"
    environment: Literal["development", "production"] = "development"
    debug: bool = False

    # ── Security ─────────────────────────────────────────────────────────
    # FIX: дефолт для локальной разработки
    secret_key: str = "dev-secret-key-change-in-production-min32!"
    access_token_expire_minutes: int = 60 * 8
    algorithm: str = "HS256"

    # ── Database ─────────────────────────────────────────────────────────
    # FIX: дефолт для локального PostgreSQL
    database_url: str = "postgresql+asyncpg://autoreports:secret@localhost:5432/autoreports"

    # ── Redis ────────────────────────────────────────────────────────────
    # FIX: дефолт для локального Redis
    redis_url: str = "redis://:redispass@localhost:6379/0"

    # ── MinIO / S3 ───────────────────────────────────────────────────────
    minio_endpoint: str = "localhost:19100"  # локальный порт из docker-compose
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_use_ssl: bool = False
    minio_bucket_sources: str = "sources"
    minio_bucket_reports: str = "reports"

    # FIX: режим локального хранилища (без MinIO)
    # "minio" | "local" — local сохраняет файлы в папку ./storage/
    storage_backend: str = "local"
    local_storage_path: str = "./storage"

    # ── LLM ──────────────────────────────────────────────────────────────
    llm_provider: Literal["ollama", "openai", "anthropic"] = "ollama"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    llm_api_key: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 8192
    llm_timeout: int = 300

    # ── Document processing ───────────────────────────────────────────────
    max_upload_size_mb: int = 50
    allowed_extensions: list[str] = [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".txt", ".png", ".jpg", ".jpeg",
    ]

    # ── Celery / задачи ───────────────────────────────────────────────────
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # FIX: синхронный режим — выполняет задачи без Redis/Celery (для локальной разработки)
    # True  = задачи выполняются синхронно прямо в process (медленно, но без Redis)
    # False = задачи через Celery (требует Redis)
    celery_task_always_eager: bool = True

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def set_celery_broker(cls, v: str, info) -> str:
        return v or info.data.get("redis_url", "")

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def set_celery_backend(cls, v: str, info) -> str:
        return v or info.data.get("redis_url", "")

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def use_local_storage(self) -> bool:
        return self.storage_backend == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
