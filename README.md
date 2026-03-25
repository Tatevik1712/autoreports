# AutoReports — Веб-сервис генерации и нормоконтроля НИР

Система автоматической генерации и проверки научно-технических отчётов (НИР) с использованием ИИ.

---

## Быстрый старт

### 1. Требования

- Docker 24+
- Docker Compose v2
- (Опционально) GPU + NVIDIA Container Toolkit для Ollama

### 2. Настройка окружения

```bash
cp .env.example .env
# Отредактируй .env — минимум поменяй SECRET_KEY
openssl rand -hex 32   # → вставь в SECRET_KEY
```

### 3. Запуск

```bash
docker compose up -d postgres redis minio
# Подождать 10–15 сек, пока поднимутся БД

docker compose up -d backend worker
# API доступен на http://localhost:8000
# Swagger: http://localhost:8000/docs
```

### 4. Применение миграций БД

```bash
docker compose exec backend alembic upgrade head
```

### 5. Создание первого администратора

```bash
docker compose exec backend python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.models import User, UserRole
from app.core.security import hash_password

async def create_admin():
    async with AsyncSessionLocal() as db:
        admin = User(
            email='admin@company.ru',
            username='admin',
            hashed_password=hash_password('changeme123'),
            role=UserRole.admin,
        )
        db.add(admin)
        await db.commit()
        print(f'Admin created: {admin.id}')

asyncio.run(create_admin())
"
```

### 6. Загрузка LLM в Ollama

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:14b
# Или меньшая модель для теста:
docker compose exec ollama ollama pull qwen2.5:7b
```

---

## Структура проекта

```
autoreports/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/    # HTTP роуты
│   │   │   ├── auth.py          # POST /auth/login, /auth/register, GET /auth/me
│   │   │   ├── templates.py     # CRUD шаблонов
│   │   │   ├── files.py         # Загрузка исходных файлов
│   │   │   └── reports.py       # Создание, статус, скачивание отчётов
│   │   ├── core/
│   │   │   ├── config.py        # Настройки (pydantic-settings)
│   │   │   ├── security.py      # JWT, хэширование паролей
│   │   │   └── logging.py       # Структурированные логи (без чувств. данных)
│   │   ├── db/
│   │   │   └── session.py       # Async SQLAlchemy engine + get_db()
│   │   ├── models/
│   │   │   └── models.py        # ORM: User, ReportTemplate, SourceFile, Report, AuditLog
│   │   ├── schemas/
│   │   │   └── schemas.py       # Pydantic v2 schemas
│   │   ├── services/
│   │   │   ├── llm/
│   │   │   │   └── provider.py  # Абстракция: Ollama / OpenAI / Anthropic
│   │   │   ├── document/
│   │   │   │   └── parser.py    # Парсинг PDF/DOCX/XLSX/TXT/изображений
│   │   │   ├── report/
│   │   │   │   ├── generator.py # Генерация секций через LLM
│   │   │   │   └── assembler.py # Сборка итогового DOCX
│   │   │   └── storage.py       # MinIO / S3 клиент
│   │   ├── workers/
│   │   │   ├── celery_app.py    # Celery конфигурация
│   │   │   └── tasks.py         # Задача process_report (полный pipeline)
│   │   └── main.py              # FastAPI app, lifespan, middleware
│   ├── alembic/                 # Миграции БД
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
├── infra/
│   └── nginx/nginx.conf
├── docs/
│   └── template_example.json   # Пример схемы шаблона НИР
├── docker-compose.yml
└── .env.example
```

---

## API — основные эндпоинты

| Метод | Путь | Описание | Роль |
|-------|------|----------|------|
| `POST` | `/api/v1/auth/login` | Получить JWT | — |
| `POST` | `/api/v1/auth/register` | Регистрация | — |
| `GET` | `/api/v1/auth/me` | Текущий пользователь | user |
| `GET` | `/api/v1/templates` | Список шаблонов | user |
| `POST` | `/api/v1/templates` | Создать шаблон | **admin** |
| `PUT` | `/api/v1/templates/{id}` | Обновить (новая версия) | **admin** |
| `POST` | `/api/v1/files` | Загрузить файл | user |
| `GET` | `/api/v1/files` | Список файлов | user |
| `POST` | `/api/v1/reports` | Создать отчёт (→ очередь) | user |
| `GET` | `/api/v1/reports/{id}` | Статус + детали | user |
| `GET` | `/api/v1/reports/{id}/download` | Скачать DOCX | user |
| `POST` | `/api/v1/reports/{id}/regenerate` | Перегенерировать | user |

---

## Pipeline обработки отчёта

```
POST /reports
    │
    ▼
[БД] Report(status=pending)
    │
    ▼
[Celery] process_report(report_id)
    │
    ├─ 1. Скачать файлы из MinIO
    ├─ 2. Парсинг (PDF/DOCX/XLSX/TXT/OCR)
    ├─ 3. Для каждой секции шаблона → LLM (Ollama)
    ├─ 4. Нормоконтроль каждой секции → LLM (валидация)
    ├─ 5. Сборка DOCX (ошибки встроены в документ)
    ├─ 6. Загрузить result.docx в MinIO
    └─ 7. [БД] Report(status=done, validation_errors=[...])

GET /reports/{id}          → статус (pending/processing/done/error)
GET /reports/{id}/download → скачать готовый DOCX
```

---

## LLM — переключение провайдера

В `.env`:

```bash
# Ollama (локальный, по умолчанию)
LLM_PROVIDER=ollama
LLM_BASE_URL=http://ollama:11434
LLM_MODEL=qwen2.5:14b

# OpenAI
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o

# Anthropic
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-6
```

Перезапуск: `docker compose restart backend worker`

---

## Дальнейшие шаги (стадия 1 → 2)

- [ ] Alembic: `alembic revision --autogenerate -m "init"` → `alembic upgrade head`
- [ ] Создать первого admin-пользователя (см. выше)
- [ ] Загрузить шаблон через `POST /api/v1/templates` (JSON из `docs/template_example.json`)
- [ ] Протестировать pipeline: загрузить PDF → создать отчёт → опросить статус → скачать
- [ ] Подключить фронтенд (React, стадия 1.3)
- [ ] Добавить RAG (ChromaDB) в стадии 2
