# Medical Learning Assistant

ИИ-ассистент для врачей и ординаторов, который помогает загружать, искать и применять знания из учебных медицинских материалов.

Проект принимает текст, веб-страницы, PDF и видео лекций, индексирует материалы в Qdrant и возвращает релевантные фрагменты или ответы с привязкой к исходным страницам и тайм-кодам.

> Статус: рабочий MVP для обучения и демонстрации. Сервис не предназначен для автономной постановки диагноза или назначения лечения.

## Что реализовано

### Источники

- текстовые материалы;
- URL с защитой от SSRF: private, loopback и link-local адреса запрещены;
- PDF с привязкой фрагментов к страницам;
- видео MP4, MOV, MKV, WEBM и M4V до 500 МБ;
- локальная транскрибация видео через `faster-whisper`;
- word-level timestamps — временные метки отдельных слов.

### Поиск и ответы

- dense semantic search в Qdrant;
- embeddings: `intfloat/multilingual-e5-large`;
- reranking: `BAAI/bge-reranker-v2-m3`;
- видео разбивается на окна максимум по 20 секунд с overlap 2 секунды;
- retrieval и reranker оценивают компактный центральный чанк;
- после ранжирования к видео-хиту добавляются предыдущий и следующий чанки;
- соседние пересекающиеся хиты дедуплицируются;
- результаты видео содержат диапазоны времени вида `3:12–4:08`;
- ответы возвращают citations, confidence, limitations и safety notes;
- доступны extractive-ответы без внешней LLM и генерация через OpenAI Responses API с extractive fallback.

### Приложение и инфраструктура

- FastAPI API `/api/v1`;
- React frontend;
- PostgreSQL для документов, indexing jobs и feedback;
- Qdrant для embeddings и metadata payload;
- Docker Compose;
- версионированные SQL-миграции;
- healthcheck, smoke test, pytest, Ruff и GitHub Actions;
- постоянные volumes для PostgreSQL, Qdrant, файлов и Hugging Face cache.

## Архитектура

```text
Browser
  -> Nginx / React frontend
      -> FastAPI routers
          -> services
              -> PostgreSQL repositories
              -> extraction / transcription
              -> embedding / reranker / answer providers
              -> Qdrant repository
```

`repository` отвечает за доступ к данным. `service` содержит бизнес-логику. Router преобразует HTTP-запрос в вызов сервиса.

Видео-поиск работает в два этапа:

```text
20-second chunks
  -> dense retrieval
  -> cross-encoder reranking
  -> select central hits
  -> fetch chunk_index - 1, chunk_index, chunk_index + 1
  -> merge context without duplicated overlap
```

Так поиск остаётся точным, а ответ получает до примерно минуты связного объяснения.

## Быстрый запуск в Docker

Требуются Docker и Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Первый запуск скачивает embedding-модель, reranker и Whisper-модель в постоянный Docker volume. На CPU это может занять заметное время.

После запуска:

- приложение: `http://127.0.0.1:3000`;
- Swagger UI: `http://127.0.0.1:8000/docs`;
- healthcheck: `http://127.0.0.1:8000/api/v1/health`.

Остановка:

```bash
docker compose down
```

Удаление контейнеров вместе с локальными данными:

```bash
docker compose down -v
```

## Демонстрационный сценарий

1. Открой `http://127.0.0.1:3000`.
2. Загрузи PDF, текст, URL или видео лекции.
3. Запусти автоматическую индексацию.
4. Дождись статуса `Готов`.
5. Выполни поиск по содержанию материала.
6. Для видео проверь тайм-коды найденных фрагментов.
7. Задай вопрос ассистенту и проверь цитаты.

## Основная конфигурация

```dotenv
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-large
EMBEDDING_DIMENSION=1024

RERANKER_BACKEND=cross-encoder
RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3

ASR_BACKEND=faster-whisper
ASR_MODEL_NAME=small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8

VIDEO_CHUNK_DURATION_SECONDS=20
VIDEO_CHUNK_OVERLAP_SECONDS=2
VIDEO_CONTEXT_NEIGHBOR_CHUNKS=1

ANSWER_BACKEND=extractive
```

`dimension` означает размерность — число компонентов embedding-вектора. После смены embedding-модели или размерности используй новое имя Qdrant collection:

```dotenv
QDRANT_COLLECTION_NAME=document_chunks_v2
```

Облегчённый режим без тяжёлых ML-зависимостей:

```dotenv
EMBEDDING_BACKEND=hash
RERANKER_BACKEND=lexical
ASR_BACKEND=disabled
QDRANT_COLLECTION_NAME=document_chunks_v1
```

Опциональный генеративный backend:

```dotenv
ANSWER_BACKEND=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

При ошибке внешней модели сервис возвращает extractive fallback и указывает ограничение в `limitations`.

## API

| Method | Endpoint | Назначение |
|---|---|---|
| `GET` | `/api/v1/health` | Проверить PostgreSQL, Qdrant и активные backend-ы |
| `POST` | `/api/v1/documents` | Создать text или URL документ |
| `POST` | `/api/v1/documents/upload` | Загрузить PDF |
| `POST` | `/api/v1/documents/upload/video` | Загрузить видео |
| `GET` | `/api/v1/documents` | Получить список документов |
| `GET` | `/api/v1/documents/{id}` | Получить документ |
| `DELETE` | `/api/v1/documents/{id}` | Удалить документ, файл и vectors |
| `POST` | `/api/v1/documents/{id}/index` | Создать indexing job |
| `GET` | `/api/v1/jobs/{id}` | Получить статус индексации |
| `POST` | `/api/v1/search` | Найти релевантные фрагменты |
| `POST` | `/api/v1/answer` | Получить ответ с citations |
| `POST` | `/api/v1/feedback` | Сохранить оценку ответа |

### Пример текстового документа

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

## Локальная разработка

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

Для настоящих ML-моделей установи зависимости:

```bash
python -m pip install -r requirements-ml.txt
```

Скрипты запускаются из корня через `python -m scripts.<name>`, чтобы пакет `app` находился в `sys.path`.

## Проверки

```bash
ruff check .
python -m pytest
```

Frontend:

```bash
cd frontend
npm install
npm run build
```

Smoke test запущенного API:

```bash
python -m scripts.smoke_test
```

Unit-тесты используют лёгкие backend-ы и не требуют PostgreSQL, Qdrant, PyTorch или внешнего API.

## Ограничения MVP

- PDF со сканами без текстового слоя не поддерживаются без OCR;
- загрузка PDF и видео пока читает файл целиком в память;
- indexing jobs выполняются внутри процесса FastAPI и не переживают его перезапуск;
- локальное файловое хранилище не подходит для нескольких backend-инстансов;
- нет authentication, authorization и пользовательской изоляции документов;
- нет rate limiting и квот на ресурсоёмкую транскрибацию;
- нет speaker diarization — разделения речи по спикерам;
- нет hybrid dense+sparse retrieval;
- нет evaluation dataset и автоматических retrieval/reranking метрик;
- CI проверяет unit-тесты и frontend build, но пока не поднимает полный Docker Compose stack.

## Перед использованием реальными пользователями

Минимально необходимы:

1. потоковая загрузка файлов или object storage;
2. отдельная очередь и worker для транскрибации и индексации;
3. authentication и разграничение доступа к материалам;
4. rate limiting, лимиты диска/CPU и наблюдаемость;
5. интеграционные и end-to-end тесты с PostgreSQL и Qdrant;
6. датасет оценки retrieval, reranking и качества ответов;
7. политика обработки медицинских и персональных данных;
8. резервное копирование PostgreSQL, Qdrant и файлового хранилища.

## Safety

Ассистент предназначен для работы с учебными материалами. Ответы нужно проверять по первичным источникам. Проект не заменяет клиническое решение врача.
