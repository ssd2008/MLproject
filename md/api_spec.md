# API-спецификация v0.3

API проекта Асси — Medical Learning Assistant.

```text
Base URL: http://127.0.0.1:8000/api/v1
Swagger UI: http://127.0.0.1:8000/docs
OpenAPI JSON: http://127.0.0.1:8000/openapi.json
```

Все JSON-запросы используют:

```http
Content-Type: application/json
```

Сервис предназначен для работы с учебными материалами и не является диагностической или лечебной системой.

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

Ошибка валидации возвращает HTTP `422`:

```json
{
  "code": "validation_error",
  "detail": "Request validation failed",
  "context": {
    "errors": []
  }
}
```

Необработанная серверная ошибка возвращает HTTP `500` и `code=internal_error`.

## Enum-значения

### `source_type`

```text
text
url
pdf
video
```

### Статус документа

```text
uploaded
processing
ready
failed
```

### Статус задания

```text
pending
running
completed
failed
```

## Health

### `GET /health`

Проверяет PostgreSQL, Qdrant и активные backend-ы.

Успешный ответ — HTTP `200`. Если PostgreSQL или Qdrant недоступны, возвращается HTTP `503`.

Пример:

```json
{
  "status": "ok",
  "service": "Medical Learning Assistant",
  "version": "0.3.0",
  "components": {
    "postgres": {"status": "ok", "detail": null},
    "qdrant": {"status": "ok", "detail": null},
    "embedding": {
      "status": "ok",
      "detail": "sentence-transformers"
    },
    "reranker": {
      "status": "ok",
      "detail": "cross-encoder"
    },
    "asr": {
      "status": "ok",
      "detail": "faster-whisper:small"
    },
    "answer": {
      "status": "ok",
      "detail": "extractive"
    }
  }
}
```

## Documents

### `POST /documents`

Создаёт документ из текста или URL.

PDF и видео через этот endpoint не принимаются: для них есть отдельные multipart endpoint-ы.

#### Текстовый документ

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

Ограничения:

- `title`: 1–300 символов;
- `raw_text`: обязателен для `source_type=text`;
- `specialty`: до 100 символов;
- `language`: 2–16 символов;
- дополнительные поля запрещены.

#### URL-документ

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

`source_url` обязателен для `source_type=url`. Backend загружает страницу и извлекает текст. Private, loopback и link-local адреса блокируются защитой от SSRF.

#### Ответ — HTTP `201`

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

Поля:

| Поле | Тип | Обязательность | Описание |
|---|---|---|---|
| `file` | binary | да | PDF-файл |
| `title` | string | да | 1–300 символов |
| `specialty` | string | нет | До 100 символов |
| `language` | string | нет | По умолчанию `ru` |
| `lecture_date` | date | нет | ISO `YYYY-MM-DD` |
| `metadata` | string | нет | JSON-объект, закодированный строкой |

Пример:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "file=@lecture.pdf" \
  -F "title=Лекция по кардиологии" \
  -F "specialty=cardiology" \
  -F "language=ru" \
  -F 'metadata={"course":"internal-medicine"}'
```

Ответ — `DocumentOut`, HTTP `201`.

Лимит по умолчанию — 10 МБ. PDF-скан без текстового слоя не поддерживается без внешнего OCR.

### `POST /documents/upload/video`

Загружает видео как `multipart/form-data`.

Поля совпадают с PDF upload:

| Поле | Тип | Обязательность |
|---|---|---|
| `file` | binary | да |
| `title` | string | да |
| `specialty` | string | нет |
| `language` | string | нет |
| `lecture_date` | date | нет |
| `metadata` | string | нет |

Пример:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload/video \
  -F "file=@lecture.mp4" \
  -F "title=Видео-лекция по неврологии" \
  -F "specialty=neurology" \
  -F "language=ru"
```

Ответ — `DocumentOut`, HTTP `201`.

Лимит по умолчанию — 500 МБ. Транскрибация выполняется локально через `faster-whisper`.

### `GET /documents`

Возвращает список документов.

Query parameters:

| Параметр | Тип | Default | Ограничение |
|---|---|---:|---|
| `limit` | integer | `50` | 1–500 |
| `offset` | integer | `0` | ≥ 0 |
| `status` | enum | — | Статус документа |
| `source_type` | enum | — | Тип источника |
| `specialty` | string | — | До 100 символов |

Пример:

```text
GET /documents?limit=20&offset=0&status=ready&source_type=pdf
```

Ответ:

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

### `GET /documents/{document_id}`

Возвращает один `DocumentOut`.

Внутренний полный текст и путь к локальному файлу не возвращаются.

### `DELETE /documents/{document_id}`

Удаляет документ, связанный локальный файл и Qdrant points.

Успешный ответ — HTTP `204` без body.

## Indexing

### `POST /documents/{document_id}/index`

Создаёт фоновое задание индексации.

Body:

```json
{
  "chunk_size": 400,
  "chunk_overlap": 80
}
```

Оба поля необязательны:

- `chunk_size`: 50–5000;
- `chunk_overlap`: 0–2000 и меньше `chunk_size`.

Если значения не переданы, используются настройки приложения.

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

Возвращает состояние задания.

```json
{
  "id": "f94a8a60-8d76-42b1-bf34-865331c4af89",
  "document_id": "88148a7c-1a7d-4cb6-8d9c-e7a23f0d50a2",
  "status": "running",
  "progress": 50,
  "chunk_size": 400,
  "chunk_overlap": 80,
  "result": {},
  "error_message": null,
  "created_at": "2026-07-17T10:01:00Z",
  "started_at": "2026-07-17T10:01:01Z",
  "finished_at": null,
  "updated_at": "2026-07-17T10:01:10Z"
}
```

`job` означает фоновую задачу. Клиент должен опрашивать endpoint до статуса `completed` или `failed`.

## Search

### `POST /search`

Ищет релевантные фрагменты.

Body:

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

Ограничения:

| Поле | Ограничение |
|---|---|
| `query` | 2–5000 символов |
| `top_k` | 1–100 |
| `candidate_k` | 1–300 и не меньше `top_k` |
| `min_retrieval_score` | `null` или `[-1, 1]` |

`top_k` — максимальное число итоговых результатов. `candidate_k` — размер первичного пула retriever.

Ответ:

```json
{
  "query": "Какие препараты применяют при гипертензии?",
  "results": [
    {
      "rank": 1,
      "chunk_id": "d69c4371-a89d-54d0-b2e9-5fd817fe09fd",
      "document_id": "88148a7c-1a7d-4cb6-8d9c-e7a23f0d50a2",
      "document_title": "Лекция по гипертензии",
      "chunk_index": 3,
      "text": "Для лечения применяют...",
      "source_type": "pdf",
      "source_url": null,
      "specialty": "cardiology",
      "lecture_date": "2026-07-14",
      "language": "ru",
      "page_start": 12,
      "page_end": 13,
      "time_start_seconds": null,
      "time_end_seconds": null,
      "section_title": null,
      "char_start": 4200,
      "char_end": 5100,
      "retrieval_score": 0.84,
      "rerank_score": 0.93,
      "final_score": 0.90
    }
  ],
  "total_candidates": 30,
  "took_ms": 145.7
}
```

С reranker:

```text
normalized_retrieval_score = clamp((retrieval_score + 1) / 2, 0, 1)
final_score = 0.25 * normalized_retrieval_score + 0.75 * rerank_score
```

Без reranker итоговый score равен нормализованному retrieval score.

Это ранжирующий показатель, а не калиброванная вероятность.

Для видео результат может содержать объединённый контекст соседних чанков и диапазон `time_start_seconds` — `time_end_seconds`.

## Answer

### `POST /answer`

Использует все поля `/search` и дополнительные настройки:

```json
{
  "query": "Кратко объясни лечение гипертензии",
  "top_k": 10,
  "candidate_k": 30,
  "use_reranker": true,
  "min_retrieval_score": null,
  "filters": {},
  "max_context_chunks": 6,
  "response_style": "detailed",
  "include_citations": true
}
```

Дополнительные ограничения:

- `max_context_chunks`: 1–30 и не больше `top_k`;
- `response_style`: `brief`, `detailed` или `study_notes`;
- `include_citations`: boolean.

Ответ:

```json
{
  "answer": "В загруженных материалах перечислены...",
  "citations": [
    {
      "number": 1,
      "document_id": "88148a7c-1a7d-4cb6-8d9c-e7a23f0d50a2",
      "chunk_id": "d69c4371-a89d-54d0-b2e9-5fd817fe09fd",
      "document_title": "Лекция по гипертензии",
      "quote": "Для лечения применяют...",
      "page_start": 12,
      "page_end": 13,
      "time_start_seconds": null,
      "time_end_seconds": null,
      "section_title": null,
      "char_start": 4200,
      "char_end": 5100,
      "retrieval_score": 0.84,
      "rerank_score": 0.93
    }
  ],
  "confidence": 0.87,
  "limitations": [],
  "safety_notes": [
    "Ответ основан только на загруженных материалах."
  ],
  "used_chunks": 3,
  "took_ms": 310.4
}
```

`confidence` — эвристический показатель, а не статистически откалиброванная вероятность.

Если OpenAI provider недоступен, сервис может вернуть extractive fallback и добавить описание проблемы в `limitations`.

## Feedback

### `POST /feedback`

Сохраняет оценку ответа.

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

Ограничения:

- `query`: 1–5000 символов;
- `answer`: 1–50000 символов;
- `rating`: только `1` или `-1`;
- `comment`: до 5000 символов.

Ответ — HTTP `201`:

```json
{
  "id": "37b142f8-4ab4-4bad-a93a-2950437428f0",
  "created_at": "2026-07-17T10:10:00Z"
}
```

## Полный cURL-сценарий

Создать текстовый документ:

```bash
DOCUMENT_ID=$(
  curl -s -X POST http://127.0.0.1:8000/api/v1/documents \
    -H 'Content-Type: application/json' \
    -d '{
      "title": "Тестовая лекция",
      "source_type": "text",
      "raw_text": "Артериальная гипертензия — стойкое повышение артериального давления.",
      "language": "ru",
      "metadata": {}
    }' | python -c "import json,sys; print(json.load(sys.stdin)['id'])"
)
```

Запустить индексацию:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/${DOCUMENT_ID}/index" \
  -H 'Content-Type: application/json' \
  -d '{}'
```

После завершения job выполнить поиск:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Что такое артериальная гипертензия?",
    "top_k": 5,
    "candidate_k": 10,
    "filters": {}
  }'
```

Для ручного тестирования удобнее использовать Swagger UI:

```text
http://127.0.0.1:8000/docs
```
