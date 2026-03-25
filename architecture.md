autoreports/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # роуты
│   │   ├── core/               # config, security, logging
│   │   ├── db/                 # session, base
│   │   ├── models/             # SQLAlchemy ORM
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # бизнес-логика
│   │   │   ├── llm/            # абстракция над LLM
│   │   │   ├── document/       # парсинг файлов
│   │   │   ├── template/       # шаблоны
│   │   │   └── report/         # генерация отчётов
│   │   └── workers/            # Celery-воркеры
│   ├── alembic/                # миграции БД
│   └── Dockerfile
├── frontend/                   # React + TypeScript (стадия 1: заглушка)
├── infra/
│   ├── docker/
│   └── nginx/
└── docker-compose.yml