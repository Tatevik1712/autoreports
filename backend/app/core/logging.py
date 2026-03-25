"""
Структурированное логирование через structlog.
Чувствительные поля автоматически маскируются.
"""
import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from backend.app.core.config import get_settings

# Поля, которые НИКОГДА не попадут в логи
_SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "authorization",
        "cookie",
        "x-api-key",
        "llm_prompt",      # промпты могут содержать данные пользователя
        "content",         # содержимое документов
    }
)


def _mask_sensitive(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Процессор: заменяет чувствительные значения на '***'."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_FIELDS:
            event_dict[key] = "***"
    return event_dict


def _add_app_context(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Добавляет общий контекст приложения."""
    settings = get_settings()
    event_dict["app"] = settings.app_name
    event_dict["env"] = settings.environment
    return event_dict


def setup_logging() -> None:
    settings = get_settings()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _mask_sensitive,
        _add_app_context,
    ]

    if settings.is_development:
        # Человекочитаемый вывод в dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON для prod (Loki/ELK)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(
        logging.DEBUG if settings.is_development else logging.INFO
    )

    # Глушим шумные библиотеки
    for noisy in ("httpx", "httpcore", "multipart", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
