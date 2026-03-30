# AutoReports — Запуск и тестирование

## Что было исправлено перед запуском

| # | Файл | Баг | Исправление |
|---|------|-----|-------------|
| 1 | `docker-compose.yml` | `command` воркера слилось с `depends_on` — контейнер не запускался | Разделены в правильные поля |
| 2 | `requirements.txt` | `chromadb` и `python-docx` дублировались — pip падал с ошибкой | Убраны дубликаты |
| 3 | `workers/tasks.py` | `db.refresh(report, ["template", "source_files"])` — asyncpg не поддерживает список атрибутов | Заменено на `selectinload` через явный `select` |
| 4 | `alembic/versions/` | Не было ни одной миграции — БД не создавалась | Добавлена `0001_init.py` со всеми таблицами |

---

## Шаг 1 — Подготовка окружения

```bash
# 1. Клонируем репозиторий (если ещё не)
git clone https://github.com/Tatevik1712/autoreports.git
cd autoreports

# 2. Создаём .env
cp .env.example .env

# 3. Редактируем .env — минимальные изменения:
#    SECRET_KEY должен быть 32+ символов
#    Остальное можно оставить по умолчанию для dev
nano .env
```

Минимальный рабочий `.env`:
```env
POSTGRES_USER=autoreports
POSTGRES_PASSWORD=secret
POSTGRES_DB=autoreports
REDIS_PASSWORD=redispass
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
SECRET_KEY=my-super-secret-key-32-chars-min!
ENVIRONMENT=development
LLM_PROVIDER=ollama
LLM_BASE_URL=http://ollama:11434
LLM_MODEL=qwen2.5:7b
```

---

## Шаг 2 — Запуск инфраструктуры

```bash
# Поднимаем PostgreSQL, Redis, MinIO
docker compose up -d postgres redis minio

# Ждём 15 секунд пока поднимутся
sleep 15

# Проверяем что все healthy
docker compose ps
# Должно быть: postgres (healthy), redis (healthy), minio (healthy)
```

---

## Шаг 3 — Сборка и запуск бэкенда

```bash
# Собираем образ (первый раз ~5 минут)
docker compose build backend worker

# Применяем миграции БД
docker compose run --rm backend alembic upgrade head
# Вывод: Running upgrade -> 0001, init

# Создаём первого администратора
docker compose run --rm backend python scripts/create_admin.py
# Вывод: [OK] Admin создан: id=...  username=admin  password=Admin123!

# Запускаем бэкенд и воркер
docker compose up -d backend worker

# Смотрим логи
docker compose logs -f backend
# Должно быть: app_startup env=development llm=ollama
```

---

## Шаг 4 — Загрузка LLM в Ollama

```bash
# Запускаем Ollama
docker compose up -d ollama

# Загружаем модель эмбеддингов (обязательно для RAG)
docker compose exec ollama ollama pull nomic-embed-text
# ~270 MB, ~1-2 минуты

# Загружаем генеративную модель
# Вариант 1: лёгкая (рекомендуется для теста, ~4.7 GB)
docker compose exec ollama ollama pull qwen2.5:7b

# Вариант 2: тяжёлая (лучше качество, ~9 GB)
docker compose exec ollama ollama pull qwen2.5:14b

# Проверяем что модели загружены
docker compose exec ollama ollama list
```

---

## Шаг 5 — Проверка что всё работает

```bash
# Healthcheck API
curl http://localhost:8000/health
# Ответ: {"status":"ok","env":"development"}

# Swagger UI
open http://localhost:8000/docs

# MinIO Console (управление файлами)
open http://localhost:9001
# Логин: minioadmin / minioadmin
```

---

## Шаг 6 — Первый полный тест через curl

### 6.1 Получаем токен
```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin123!" \
  | python3 -m json.tool

# Сохраняем токен
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin123!" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"
```

### 6.2 Создаём шаблон НИР
```bash
curl -s -X POST http://localhost:8000/api/v1/templates \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @docs/template_example.json \
  | python3 -m json.tool

# Сохраняем ID шаблона
TEMPLATE_ID=$(curl -s http://localhost:8000/api/v1/templates \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['items'][0]['id'])")

echo "Template ID: $TEMPLATE_ID"
```

### 6.3 Загружаем тестовый документ
```bash
# Нужен любой PDF или DOCX — пример с тестовым txt
echo "Введение. В данной работе рассматривается методика испытаний материалов.
Методика. Испытания проводились при температуре 20°C.
Образцы размером 10х10 мм нагружались со скоростью 2 мм/мин.
Результаты. Предел прочности составил 450 МПа.
Относительное удлинение — 12%.
Заключение. Материал соответствует требованиям ГОСТ 1050-2013." \
> /tmp/test_report.txt

FILE_ID=$(curl -s -X POST http://localhost:8000/api/v1/files \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test_report.txt" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "File ID: $FILE_ID"
```

### 6.4 Запускаем генерацию отчёта
```bash
REPORT_ID=$(curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"Тестовый отчёт НИР\",
    \"template_id\": \"$TEMPLATE_ID\",
    \"source_file_ids\": [\"$FILE_ID\"]
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Report ID: $REPORT_ID"
echo "Статус: PENDING — задача отправлена в очередь"
```

### 6.5 Следим за статусом
```bash
# Проверяем каждые 10 секунд
watch -n 10 "curl -s http://localhost:8000/api/v1/reports/$REPORT_ID \
  -H 'Authorization: Bearer $TOKEN' \
  | python3 -m json.tool"

# Когда status станет "done" — скачиваем
curl -s http://localhost:8000/api/v1/reports/$REPORT_ID \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Status:', d['status'])"
```

### 6.6 Скачиваем готовый DOCX
```bash
curl -o result.docx \
  http://localhost:8000/api/v1/reports/$REPORT_ID/download \
  -H "Authorization: Bearer $TOKEN"

echo "Файл сохранён: result.docx"
open result.docx   # macOS
# xdg-open result.docx  # Linux
```

### 6.7 Смотрим debug-информацию по RAG
```bash
curl -s http://localhost:8000/api/v1/debug/reports/$REPORT_ID/retrieval \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool
```

---

## Мониторинг и диагностика

### Логи в реальном времени
```bash
# Все сервисы
docker compose logs -f

# Только бэкенд
docker compose logs -f backend

# Только воркер (тут видна генерация)
docker compose logs -f worker

# Только Ollama (тут видно время инференса)
docker compose logs -f ollama
```

### Состояние Celery очереди
```bash
docker compose exec worker \
  celery -A app.workers.celery_app inspect active

docker compose exec worker \
  celery -A app.workers.celery_app inspect stats
```

### Проверка ChromaDB
```bash
docker compose exec backend python3 -c "
import chromadb
client = chromadb.PersistentClient('/app/data/chromadb')
print('Collections:', client.list_collections())
"
```

### Проверка подключения к Ollama
```bash
curl http://localhost:11434/api/tags
```

---

## Типичные ошибки и решения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `connection refused :8000` | backend не запустился | `docker compose logs backend` |
| `alembic: target database is not up to date` | Миграции не применены | `docker compose run --rm backend alembic upgrade head` |
| `WORKER: Process 'ForkPoolWorker-1' exited` | Нет памяти или Ollama недоступен | Проверить `docker compose logs ollama` |
| `chromadb: no such file or directory` | Volume не создан | `docker compose down -v && docker compose up` |
| `401 Unauthorized` | Токен протух (8 ч) | Повторить логин |
| `Report status: error` | Ошибка генерации | `GET /debug/reports/{id}/retrieval` |
| Ollama timeout | Модель слишком большая | Переключить на `qwen2.5:7b` в `.env` |

---

## Что дальше в проекте

### Готово ✅
- Полная инфраструктура (Docker Compose)
- БД с миграциями (PostgreSQL + Alembic)
- Auth (JWT, роли user/admin)
- Загрузка файлов (PDF, DOCX, XLSX, TXT, изображения)
- RAG pipeline (chunker → embeddings → ChromaDB + BM25 → reranking)
- Генерация DOCX с нормоконтролем
- Async очередь задач (Celery + Redis)
- Хранилище файлов (MinIO)
- Debug API

### Нужно сделать 🔧
- [ ] **Фронтенд** (React) — сейчас только API, нет UI
- [ ] **Тесты** — unit для chunker/parser, integration для pipeline
- [ ] **Перегенерация** — проверить что `POST /reports/{id}/regenerate` работает
- [ ] **Паспорт ИС** — документация для заказчика
- [ ] **LDAP/OpenID** — корпоративная авторизация (стадия 3)
- [ ] **Prometheus метрики** — мониторинг (стадия 3)
