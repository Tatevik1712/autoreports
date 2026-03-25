"""
Клиент для работы с MinIO (S3-совместимое хранилище).
"""
from __future__ import annotations

import io

import aioboto3
from botocore.exceptions import ClientError

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class StorageClient:
    """Async MinIO / S3 клиент."""

    def __init__(self) -> None:
        self.bucket_sources = settings.minio_bucket_sources
        self.bucket_reports = settings.minio_bucket_reports
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
        """Создаёт бакеты при запуске, если они не существуют."""
        async with self._client() as s3:
            for bucket in (self.bucket_sources, self.bucket_reports):
                try:
                    await s3.head_bucket(Bucket=bucket)
                except ClientError:
                    await s3.create_bucket(Bucket=bucket)
                    logger.info("storage_bucket_created", bucket=bucket)

    async def upload(
        self,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Загружает файл, возвращает ключ."""
        async with self._client() as s3:
            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
        logger.debug("storage_upload", bucket=bucket, key=key, size=len(content))
        return key

    async def download(self, bucket: str, key: str) -> bytes:
        """Скачивает файл, возвращает байты."""
        async with self._client() as s3:
            response = await s3.get_object(Bucket=bucket, Key=key)
            content = await response["Body"].read()
        logger.debug("storage_download", bucket=bucket, key=key, size=len(content))
        return content

    async def delete(self, bucket: str, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=bucket, Key=key)

    async def get_presigned_url(
        self, bucket: str, key: str, expires_in: int = 3600
    ) -> str:
        """Presigned URL для скачивания без авторизации (временный)."""
        async with self._client() as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        return url


_storage: StorageClient | None = None


def get_storage_client() -> StorageClient:
    global _storage
    if _storage is None:
        _storage = StorageClient()
    return _storage
