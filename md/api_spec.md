# API-спецификация v0.3

API проекта Асси — Medical Learning Assistant.

```text
Base URL: http://127.0.0.1:8000/api/v1
Swagger UI: http://127.0.0.1:8000/docs
OpenAPI JSON: http://127.0.0.1:8000/openapi.json
```

Все JSON-запросы используют `Content-Type: application/json`. Сервис предназначен для работы с учебными материалами и не является диагностической или лечебной системой.

## Основной режим поиска

По умолчанию API использует Dense retrieval:

```text
intfloat/multilingual-e5-large
  -> normalized embeddings
  -> Qdrant cosine search
  -> ranked chunks
```

Reranker является экспериментальной опцией и отключён глобально:

```dotenv
RERANKER_ENABLED=false
```

Для его фактического использования одновременно нужны:

1. `RERANKER_ENABLED=true` в конфигурации сервера;
2. `use_reranker=true` в запросе `/search` или `/answer`.

Если глобальный флаг выключен, запрос обрабатывается через Dense retrieval, даже когда клиент передал `use_reranker=true`. В таком ответе `rerank_score=null`.

Dense выбран по результатам воспроизводимого benchmark: `Recall@5=0.983`, `MRR=0.865`, `Top-1 gold accuracy=78.3%`, p50 latency `0.297` секунды. Подробности: [retrieval benchmark](../evaluation/README.md).

## Краткая сводка API

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/health` | Проверка PostgreSQL, Qdrant и настроенных backend-ов |
| `POST` | `/documents` | Создание документа из текста или URL |
| `POST` | `/documents/upload` | Загрузка PDF-документа |
| `POST` | `/documents/upload/video` | Загрузка видео для транскрибации |
| `GET` | `/documents` | Получение списка документов |
| `GET` | `/documents/{document_id}` | Получение одного документа |
| `POST` | `/documents/{document_id}/index` | Индексация или переиндексация документа |
| `DELETE` | `/documents/{document_id}` | Удаление документа и его векторов |
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

Выполняет реальные проверки PostgreSQL и Qdrant. ML-модели не загружаются и тестовый inference не выполняется.

Стандартный ответ:

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
      "status": "disabled",
      "detail": null
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

При `RERANKER_ENABLED=true` компонент `reranker` имеет `status=ok` и detail вида `configured:cross-encoder`.

HTTP `200` означает, что PostgreSQL и Qdrant доступны. При ошибке одного из них возвращается HTTP `503` и `status=degraded`.

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

URL-загрузка разрешает только публичные HTTP(S)-адреса. Локальные и специальные IP-диапазоны, URL со встроенными credentials и небезопасные redirects блокируются.

Успешный ответ — HTTP `201`, модель `DocumentOut`.

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

Лимит по умолчанию — 10 МБ. PDF-скан без текстового слоя не поддерживается без внешнего OCR.

### `POST /documents/upload/video`

Загружает видео как `multipart/form-data`. Поля совпадают с PDF upload.

Поддерживаются `.mp4`, `.mov`, `.mkv`, `.webm` и `.m4v`. Лимит по умолчанию — 2 ГБ. Транскрибация выполняется локально через `faster-whisper`.

### `GET /documents`

Query parameters:

| Параметр | Тип | Default | Ограничение |
|---|---|---:|---|
| `limit` | integer | `50` | 1–500 |
| `offset` | integer | `0` | ≥ 0 |
| `status` | enum | — | Статус документа |
| `source_type` | enum | — | Тип источника |
| `specialty` | string | — | До 100 символов |

Ответ содержит `items`, `total`, `limit` и `offset`.

### `GET /documents/{document_id}`

Возвращает один `DocumentOut`. Полный исходный текст и локальный путь к файлу не возвращаются.

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

Pipeline:

```text
source extraction / transcription
  -> chunks with overlap
  -> dense embeddings
  -> delete previous document points
  -> Qdrant upsert
  -> document status ready
```

Успешный ответ — HTTP `202` с `document_id`, `job_id` и `status=pending`.

### `GET /jobs/{job_id}`

Возвращает состояние задания, progress, result, error message и timestamps. Клиент должен опрашивать endpoint до статуса `completed` или `failed`.

## Search

### `POST /search`

Стандартный dense-запрос:

```json
{
  "query": "Какие препараты применяют при гипертензии?",
  "top_k": 10,
  "candidate_k": 30,
  "use_reranker": false,
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

| Поле | Default | Ограничение |
|---|---:|---|
| `query` | — | 2–5000 символов |
| `top_k` | `10` | 1–100 |
| `candidate_k` | `30` | 1–300 и не меньше `top_k` |
| `use_reranker` | `false` | boolean |
| `min_retrieval_score` | `null` | `null` или `[-1, 1]` |

В основном режиме:

```text
final_score = clamp((retrieval_score + 1) / 2, 0, 1)
rerank_score = null
```

`retrieval_score` — similarity score Qdrant. `final_score` — нормализованный ранжирующий показатель, а не калиброванная вероятность правильности.

### Экспериментальный reranking

Сначала включи серверную опцию:

```dotenv
RERANKER_ENABLED=true
```

Затем передай:

```json
{
  "use_reranker": true
}
```

В этом режиме:

```text
normalized_retrieval_score = clamp((retrieval_score + 1) / 2, 0, 1)
final_score = 0.25 * normalized_retrieval_score + 0.75 * rerank_score
```

Reranker не рекомендуется как production-default текущего MVP: в проведённом benchmark он ухудшил MRR и Top-1 gold accuracy и увеличил p50 latency до `5.525` секунды.

Для видео результат может содержать объединённый контекст соседних чанков и диапазон `time_start_seconds` — `time_end_seconds`.

## Answer

### `POST /answer`

Использует поля `/search` и дополнительные настройки:

```json
{
  "query": "Кратко объясни лечение гипертензии",
  "top_k": 10,
  "candidate_k": 30,
  "use_reranker": false,
  "filters": {},
  "max_context_chunks": 6,
  "response_style": "detailed",
  "include_citations": true
}
```

- `max_context_chunks`: 1–30 и не больше `top_k`;
- `response_style`: `brief`, `detailed` или `study_notes`;
- `include_citations`: boolean.

Ответ содержит:

- `answer`;
- `citations`;
- `confidence`;
- `limitations`;
- `safety_notes`;
- `used_chunks`;
- `took_ms`.

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
