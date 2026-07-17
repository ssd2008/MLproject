# API-спецификация v0.3

API проекта Асси — Medical Learning Assistant.

```text
Base URL: http://127.0.0.1:8000/api/v1
Swagger UI: http://127.0.0.1:8000/docs
OpenAPI JSON: http://127.0.0.1:8000/openapi.json
```

Все JSON-запросы используют `Content-Type: application/json`. Сервис предназначен для работы с учебными материалами и не является диагностической или лечебной системой.

## Краткая сводка API

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/health` | Проверка PostgreSQL, Qdrant и списка настроенных backend-ов |
| `POST` | `/documents` | Создание документа из текста или URL |
| `POST` | `/documents/upload` | Загрузка PDF-документа |
| `POST` | `/documents/upload/video` | Загрузка видео для транскрибации и индексации |
| `GET` | `/documents` | Получение списка документов |
| `GET` | `/documents/{document_id}` | Получение информации о документе |
| `POST` | `/documents/{document_id}/index` | Запуск или повторный запуск индексации |
| `DELETE` | `/documents/{document_id}` | Удаление документа, файла и векторного индекса |
| `GET` | `/jobs/{job_id}` | Получение состояния фоновой задачи |
| `POST` | `/search` | Поиск релевантных фрагментов |
| `POST` | `/answer` | Формирование ответа по найденным фрагментам |
| `POST` | `/feedback` | Сохранение пользовательской оценки |

## Общий формат ошибок

```json
{
  "code": "document_not_found",
  "detail": "Document not found",
  "context": {
    "document_id": "..."
  }
}
```

Ошибка валидации возвращает HTTP `422` с `code=validation_error`. Необработанная серверная ошибка возвращает HTTP `500` с `code=internal_error`.

## Enum-значения

`source_type`:

```text
text
url
pdf
video
```

Статус документа:

```text
uploaded
processing
ready
failed
```

Статус задания:

```text
pending
running
completed
failed
```

## Health

### `GET /health`

Выполняет реальные проверки доступности PostgreSQL и Qdrant. Для embedding, reranker, ASR и answer возвращает настроенную реализацию, но не загружает модель и не запускает тестовый inference.

HTTP `200` означает, что PostgreSQL и Qdrant доступны. При ошибке одного из них возвращается HTTP `503` и `status=degraded`.

```json
{
  "status": "ok",
  "service": "Асси — Medical Learning Assistant",
  "version": "0.3.0",
  "components": {
    "postgres": {"status": "ok", "detail": null},
    "qdrant": {"status": "ok", "detail": null},
    "embedding": {
      "status": "ok",
      "detail": "configured:sentence-transformers"
    },
    "reranker": {
      "status": "ok",
      "detail": "configured:cross-encoder"
    },
    "asr": {
      "status": "ok",
      "detail": "configured:faster-whisper:small"
    },
    "answer": {
      "status": "ok",
      "detail": "configured:extractive"
    }
  }
}
```

## Documents

### `POST /documents`

Создаёт документ из текста или URL. PDF и видео принимаются отдельными multipart endpoint-ами.

Текстовый документ:

```json
{
  "title": "Лекция по артериальной гипертензии",
  "source_type": "text",
  "raw_text": "Полный текст лекции...",
  "specialty": "cardiology",
  "lecture_date": "2026-07-14",
  "language": "ru",
  "metadata": {
    "course": "internal-medicine"
  }
}
```

URL-документ:

```json
{
  "title": "Материал курса",
  "source_type": "url",
  "source_url": "https://example.org/lecture",
  "specialty": null,
  "lecture_date": null,
  "language": "ru",
  "metadata": {}
}
```

Ограничения:

- `title`: 1–300 символов;
- `raw_text`: обязателен для `source_type=text`;
- `source_url`: обязателен для `source_type=url`;
- `specialty`: до 100 символов;
- `language`: 2–16 символов;
- дополнительные JSON-поля запрещены.

При загрузке URL backend разрешает только абсолютные HTTP(S)-адреса. Каждый redirect проверяется до следующего запроса; локальные и специальные IP-диапазоны, URL со встроенными credentials и неподдерживаемые типы ответа блокируются.

Успешный ответ — HTTP `201`, модель `DocumentOut`:

```json
{
  "id": "88148a7c-1a7d-4cb6-8d9c-e7a23f0d50a2",
  "title": "Лекция по артериальной гипертензии",
  "source_type": "text",
  "status": "uploaded",
  "source_url": null,
  "original_filename": null,
  "mime_type": null,
  "size_bytes": null,
  "specialty": "cardiology",
  "lecture_date": "2026-07-14",
  "language": "ru",
  "metadata": {},
  "chunk_count": 0,
  "error_message": null,
  "created_at": "2026-07-17T10:00:00Z",
  "updated_at": "2026-07-17T10:00:00Z"
}
```

### `POST /documents/upload`

Загружает PDF как `multipart/form-data`.

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `file` | binary | да | PDF-файл |
| `title` | string | да | 1–300 символов |
| `specialty` | string | нет | До 100 символов |
| `language` | string | нет | По умолчанию `ru` |
| `lecture_date` | date | нет | ISO `YYYY-MM-DD` |
| `metadata` | string | нет | JSON-объект, закодированный строкой |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "file=@lecture.pdf" \
  -F "title=Лекция по кардиологии" \
  -F "specialty=cardiology" \
  -F "language=ru"
```

Ответ — `DocumentOut`, HTTP `201`. Лимит по умолчанию — 10 МБ. PDF-скан без текстового слоя не поддерживается без внешнего OCR.

### `POST /documents/upload/video`

Загружает видео как `multipart/form-data`. Поля совпадают с PDF upload.

Поддерживаются `.mp4`, `.mov`, `.mkv`, `.webm` и `.m4v`. Лимит по умолчанию — 500 МБ. Транскрибация выполняется локально через `faster-whisper`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload/video \
  -F "file=@lecture.mp4" \
  -F "title=Видео-лекция по неврологии" \
  -F "specialty=neurology" \
  -F "language=ru"
```

### `GET /documents`

Query parameters:

| Параметр | Тип | Default | Ограничение |
|---|---|---:|---|
| `limit` | integer | `50` | 1–500 |
| `offset` | integer | `0` | ≥ 0 |
| `status` | enum | — | Статус документа |
| `source_type` | enum | — | Тип источника |
| `specialty` | string | — | До 100 символов |

```text
GET /documents?limit=20&offset=0&status=ready&source_type=pdf
```

Ответ содержит `items`, `total`, `limit` и `offset`.

### `GET /documents/{document_id}`

Возвращает один `DocumentOut`. Внутренний полный текст и путь к локальному файлу не возвращаются.

### `DELETE /documents/{document_id}`

Удаляет документ, связанный локальный файл и Qdrant points. Успешный ответ — HTTP `204` без body.

## Indexing

### `POST /documents/{document_id}/index`

Создаёт фоновое задание индексации.

```json
{
  "chunk_size": 400,
  "chunk_overlap": 80
}
```

- `chunk_size`: 50–5000;
- `chunk_overlap`: 0–2000 и меньше `chunk_size`;
- оба поля необязательны.

Ответ — HTTP `202`:

```json
{
  "document_id": "88148a7c-1a7d-4cb6-8d9c-e7a23f0d50a2",
  "job_id": "f94a8a60-8d76-42b1-bf34-865331c4af89",
  "status": "pending"
}
```

Pipeline:

```text
source extraction / transcription
  -> chunks with overlap
  -> embeddings
  -> delete previous document points
  -> Qdrant upsert
  -> document status ready
```

### `GET /jobs/{job_id}`

Возвращает состояние задания, progress, result, error message и timestamps. Клиент должен опрашивать endpoint до статуса `completed` или `failed`.

## Search

### `POST /search`

```json
{
  "query": "Какие препараты применяют при гипертензии?",
  "top_k": 10,
  "candidate_k": 30,
  "use_reranker": true,
  "min_retrieval_score": null,
  "filters": {
    "document_ids": null,
    "specialty": "cardiology",
    "source_types": ["text", "pdf", "video"],
    "language": "ru",
    "lecture_date_from": null,
    "lecture_date_to": null
  }
}
```

| Поле | Ограничение |
|---|---|
| `query` | 2–5000 символов |
| `top_k` | 1–100 |
| `candidate_k` | 1–300 и не меньше `top_k` |
| `min_retrieval_score` | `null` или `[-1, 1]` |

С reranker:

```text
normalized_retrieval_score = clamp((retrieval_score + 1) / 2, 0, 1)
final_score = 0.25 * normalized_retrieval_score + 0.75 * rerank_score
```

Без reranker итоговый score равен нормализованному retrieval score. Это ранжирующий показатель, а не калиброванная вероятность.

Для видео результат может содержать объединённый контекст соседних чанков и диапазон `time_start_seconds` — `time_end_seconds`.

## Answer

### `POST /answer`

Использует поля `/search` и дополнительные настройки:

```json
{
  "query": "Кратко объясни лечение гипертензии",
  "top_k": 10,
  "candidate_k": 30,
  "use_reranker": true,
  "filters": {},
  "max_context_chunks": 6,
  "response_style": "detailed",
  "include_citations": true
}
```

- `max_context_chunks`: 1–30 и не больше `top_k`;
- `response_style`: `brief`, `detailed` или `study_notes`;
- `include_citations`: boolean.

Ответ содержит `answer`, `citations`, `confidence`, `limitations`, `safety_notes`, `used_chunks` и `took_ms`.

`confidence` — эвристический показатель, а не статистически откалиброванная вероятность. По умолчанию используется локальный extractive backend.

## Feedback

### `POST /feedback`

```json
{
  "query": "Какие препараты применяют?",
  "answer": "В материалах указаны...",
  "rating": 1,
  "comment": "Полезный ответ",
  "document_ids": [
    "88148a7c-1a7d-4cb6-8d9c-e7a23f0d50a2"
  ],
  "metadata": {
    "client": "web"
  }
}
```

- `query`: 1–5000 символов;
- `answer`: 1–50000 символов;
- `rating`: только `1` или `-1`;
- `comment`: до 5000 символов.

Ответ — HTTP `201` с `id` и `created_at`.

## Полный cURL-сценарий

Создать текстовый документ:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Тестовая лекция",
    "source_type": "text",
    "raw_text": "Артериальная гипертензия — стойкое повышение артериального давления.",
    "language": "ru",
    "metadata": {}
  }'
```

После получения `document_id` запусти индексацию:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/DOCUMENT_ID/index" \
  -H 'Content-Type: application/json' \
  -d '{}'
```

Для ручного тестирования удобнее использовать Swagger UI:

```text
http://127.0.0.1:8000/docs
```
