"""
Клиент для работы с файлами.
Два бэкенда:
  - LocalStorageClient  — сохраняет файлы на диск (для локальной разработки)
  - MinIOStorageClient  — S3-совместимый MinIO (для Docker / prod)

Выбор через config: storage_backend = "local" | "minio"
"""
from __future__ import annotations

import os
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Интерфейс (общий для обоих бэкендов)
# ─────────────────────────────────────────────────────────────────────────────

class BaseStorageClient:
    bucket_sources: str
    bucket_reports: str

    async def ensure_buckets(self) -> None: ...
    async def upload(self, bucket: str, key: str, content: bytes, content_type: str = "application/octet-stream") -> str: ...
    async def download(self, bucket: str, key: str) -> bytes: ...
    async def delete(self, bucket: str, key: str) -> None: ...


# ─────────────────────────────────────────────────────────────────────────────
# Локальное хранилище (папка на диске)
# ─────────────────────────────────────────────────────────────────────────────

class LocalStorageClient(BaseStorageClient):
    """
    Хранит файлы в папке ./storage/{bucket}/{key}.
    Не требует MinIO — удобно для локальной разработки и тестирования.
    """

    def __init__(self) -> None:
        self.bucket_sources = settings.minio_bucket_sources
        self.bucket_reports = settings.minio_bucket_reports
        self._base = Path(settings.local_storage_path)

    async def ensure_buckets(self) -> None:
        for bucket in (self.bucket_sources, self.bucket_reports):
            (self._base / bucket).mkdir(parents=True, exist_ok=True)
            logger.info("local_storage_bucket_ready", path=str(self._base / bucket))

    async def upload(self, bucket: str, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._base / bucket / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        logger.debug("local_storage_upload", bucket=bucket, key=key, size=len(content))
        return key

    async def download(self, bucket: str, key: str) -> bytes:
        path = self._base / bucket / key
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {bucket}/{key}")
        content = path.read_bytes()
        logger.debug("local_storage_download", bucket=bucket, key=key, size=len(content))
        return content

    async def delete(self, bucket: str, key: str) -> None:
        path = self._base / bucket / key
        if path.exists():
            path.unlink()
            logger.debug("local_storage_delete", bucket=bucket, key=key)

    async def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        # Для локального хранилища — прямой путь
        return f"/local-storage/{bucket}/{key}"


# ─────────────────────────────────────────────────────────────────────────────
# MinIO / S3 (для Docker / prod)
# ─────────────────────────────────────────────────────────────────────────────

class MinIOStorageClient(BaseStorageClient):
    """Async MinIO / S3 клиент."""

    def __init__(self) -> None:
        self.bucket_sources = settings.minio_bucket_sources
        self.bucket_reports = settings.minio_bucket_reports
        import aioboto3
        self._session = aioboto3.Session()
        self._endpoint = (
            f"{'https' if settings.minio_use_ssl else 'http'}://{settings.minio_endpoint}"
        )

    def _client(self):
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        )

    async def ensure_buckets(self) -> None:
        from botocore.exceptions import ClientError
        async with self._client() as s3:
            for bucket in (self.bucket_sources, self.bucket_reports):
                try:
                    await s3.head_bucket(Bucket=bucket)
                except ClientError:
                    await s3.create_bucket(Bucket=bucket)
                    logger.info("minio_bucket_created", bucket=bucket)

    async def upload(self, bucket: str, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        async with self._client() as s3:
            await s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)
        logger.debug("minio_upload", bucket=bucket, key=key, size=len(content))
        return key

    async def download(self, bucket: str, key: str) -> bytes:
        async with self._client() as s3:
            response = await s3.get_object(Bucket=bucket, Key=key)
            content = await response["Body"].read()
        logger.debug("minio_download", bucket=bucket, key=key, size=len(content))
        return content

    async def delete(self, bucket: str, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=bucket, Key=key)

    async def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        async with self._client() as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Фабрика
# ─────────────────────────────────────────────────────────────────────────────

_storage: BaseStorageClient | None = None


def get_storage_client() -> BaseStorageClient:
    global _storage
    if _storage is None:
        if settings.use_local_storage:
            logger.info("storage_backend", backend="local", path=settings.local_storage_path)
            _storage = LocalStorageClient()
        else:
            logger.info("storage_backend", backend="minio", endpoint=settings.minio_endpoint)
            _storage = MinIOStorageClient()
    return _storage
