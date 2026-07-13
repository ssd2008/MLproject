# Medical Learning Assistant — backend

Backend для ИИ-ассистента, который загружает медицинские учебные материалы, индексирует их в Qdrant, выполняет semantic search, reranking и возвращает ответы с цитатами.

Проект предназначен для обучения. Он не должен использоваться для автономной постановки диагноза или назначения лечения.

## Что реализовано

- FastAPI API `/api/v1`;
- загрузка текста, URL и PDF;
- защита URL-загрузки от SSRF: private/loopback/link-local адреса запрещены;
- извлечение текста из PDF с привязкой chunks к страницам;
- deterministic chunking с overlap и точными `char_start` / `char_end`;
- PostgreSQL для документов, indexing jobs и feedback;
- Qdrant для embeddings и payload;
- идемпотентная переиндексация документа;
- два embedding backend-а:
  - `hash` — лёгкий backend без PyTorch для разработки и тестов;
  - `sentence-transformers` — `multilingual-e5-large`;
- два reranker backend-а:
  - `lexical` — лёгкий fallback;
  - `cross-encoder` — BGE reranker;
- два answer backend-а:
  - `extractive` — ответ из найденных фрагментов без LLM;
  - `openai` — генерация через Responses API с extractive fallback;
- citations, confidence, limitations и safety notes;
- Docker Compose, миграции, smoke test, pytest, Ruff и GitHub Actions.

## Архитектура

```text
HTTP API
  -> services
      -> PostgreSQL repositories
      -> embedding/reranker/answer providers
      -> Qdrant repository
```

`repository` отвечает только за доступ к данным. `service` реализует бизнес-логику. Router преобразует HTTP-запрос в вызов сервиса.

## Быстрый запуск в Docker

```bash
cp .env.example .env
docker compose up --build
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

Healthcheck:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Smoke test:

```bash
python -m scripts.smoke_test
```

## Локальный запуск

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d postgres qdrant
python -m scripts.migrate
uvicorn app.main:app --reload
```

Запускай скрипты через `python -m scripts.<name>` из корня проекта. Тогда корень проекта находится в `sys.path`, и импорт `app` работает без ручного `PYTHONPATH`.

## Настоящие ML-модели

Базовая конфигурация использует `hash` и `lexical`, чтобы backend запускался без тяжёлых зависимостей.

Сначала установи подходящий для твоей ОС и версии Python PyTorch, затем:

```bash
python -m pip install -r requirements-ml.txt
```

В `.env`:

```dotenv
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-large
EMBEDDING_DIMENSION=1024
RERANKER_BACKEND=cross-encoder
RERANKER_MODEL_NAME=BAAI/bge-reranker-large
```

После смены `EMBEDDING_DIMENSION` или embedding-модели используй новое имя коллекции, например:

```dotenv
QDRANT_COLLECTION_NAME=document_chunks_v2
```

Векторная размерность коллекции фиксируется при создании. `dimension` означает размерность — число компонентов embedding-вектора.

## OpenAI answer backend

```dotenv
ANSWER_BACKEND=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

При ошибке внешней модели сервис не теряет ответ полностью: он возвращает extractive fallback и записывает ограничение в `limitations`.

## API

Основные endpoints:

| Method | Endpoint | Назначение |
|---|---|---|
| `GET` | `/api/v1/health` | Проверка PostgreSQL, Qdrant и активных backend-ов |
| `POST` | `/api/v1/documents` | Создать text/URL документ |
| `POST` | `/api/v1/documents/upload` | Загрузить PDF |
| `GET` | `/api/v1/documents` | Список документов |
| `GET` | `/api/v1/documents/{id}` | Получить документ |
| `DELETE` | `/api/v1/documents/{id}` | Удалить документ и vectors |
| `POST` | `/api/v1/documents/{id}/index` | Создать background indexing job |
| `GET` | `/api/v1/jobs/{id}` | Статус индексации |
| `POST` | `/api/v1/search` | Поиск chunks |
| `POST` | `/api/v1/answer` | Ответ с citations |
| `POST` | `/api/v1/feedback` | Сохранить оценку ответа |

### Создание текстового документа

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Лекция по гипертензии",
    "source_type": "text",
    "raw_text": "Полный текст лекции...",
    "specialty": "cardiology",
    "language": "ru"
  }'
```

### Индексация

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/<UUID>/index \
  -H 'Content-Type: application/json' \
  -d '{"chunk_size": 400, "chunk_overlap": 80}'
```

`job` означает фоновую задачу. Endpoint сразу возвращает `job_id`; прогресс читается через `/jobs/{job_id}`.

## Тесты и линтер

```bash
pytest
ruff check .
```

Unit-тесты не требуют PostgreSQL, Qdrant, PyTorch или внешнего API.

## Ограничения текущей версии

- PDF со сканами без текстового слоя требует отдельного OCR pipeline;
- background jobs выполняются процессом FastAPI, а не отдельной очередью Celery/RQ;
- `hash` embeddings и `lexical` reranker нужны для запуска, но не заменяют ML-модели по качеству;
- локальное файловое хранилище PDF нужно заменить на S3-совместимое для нескольких backend-инстансов;
- нет authentication/authorization и пользовательской изоляции документов;
- нет hybrid dense+sparse retrieval;
- нет evaluation dataset и автоматической оценки retrieval/reranking quality.
