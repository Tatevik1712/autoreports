"""
Celery-воркер: асинхронная обработка задач генерации отчётов.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import Celery
from celery.utils.log import get_task_logger

from backend.app.core.config import get_settings

settings = get_settings()
logger = get_task_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Celery app
# ─────────────────────────────────────────────────────────────────────────────

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
    task_acks_late=True,          # подтверждаем ПОСЛЕ завершения (надёжность)
    worker_prefetch_multiplier=1, # не берём больше одной задачи за раз
    task_routes={
        "app.workers.tasks.process_report": {"queue": "reports"},
    },
    result_expires=60 * 60 * 24,  # результаты хранятся 24 часа
)
