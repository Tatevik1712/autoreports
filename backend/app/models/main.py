"""
Точка входа FastAPI-приложения.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте, очистка при остановке."""
    logger.info("app_startup", env=settings.environment, llm=settings.llm_provider)

    # Создаём бакеты в MinIO, если их нет
    from app.services.storage import get_storage_client
    await get_storage_client().ensure_buckets()

    # Прогрев LLM-соединения (не блокирует, просто логирует)
    try:
        from app.services.llm.provider import get_llm_provider
        get_llm_provider()
        logger.info("llm_provider_ready", provider=settings.llm_provider)
    except Exception as exc:
        logger.warning("llm_provider_init_failed", error=str(exc))

    yield

    logger.info("app_shutdown")


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AutoReports API",
    description="Веб-сервис генерации и нормоконтроля НТД с использованием ИИ",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# CORS (в prod — ограничить до конкретных origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Global exception handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        method=request.method,
        url=str(request.url),
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Внутренняя ошибка сервера"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Healthcheck для Docker / Kubernetes."""
    return {"status": "ok", "env": settings.environment}
