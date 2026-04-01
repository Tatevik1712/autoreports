"""
Celery-воркер.
FIX: в режиме разработки (celery_task_always_eager=True) задачи
выполняются синхронно без Redis — удобно для локального тестирования.
"""
from __future__ import annotations

from celery import Celery
from celery.utils.log import get_task_logger

from app.core.config import get_settings

settings = get_settings()
logger = get_task_logger(__name__)

celery_app = Celery(
    "autoreports",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.process_report": {"queue": "reports"},
    },
    result_expires=60 * 60 * 24,
    # FIX: синхронный режим для локальной разработки (без Redis)
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,  # пробрасывает исключения при eager режиме
)
