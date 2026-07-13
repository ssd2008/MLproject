# API Spec v0.1 — Medical Study Assistant

## 0. Назначение

API предназначено для MVP системы:

> ИИ-ассистент для врачей и ординаторов, помогающий суммаризировать, находить и применять знания из учебных медицинских материалов.

Основной сценарий:

```text
пользователь задаёт вопрос
→ система ищет релевантные фрагменты в учебных материалах
→ reranker уточняет порядок фрагментов
→ LLM формирует структурированный ответ
→ API возвращает ответ, источники, confidence и safety-блок
```

Важно: система предназначена для обучения и работы с материалами, а не для самостоятельной постановки диагноза или назначения лечения.

---

# 1. Краткая спецификация

Базовый URL:

```text
/api/v1
```

Формат данных:

```text
Content-Type: application/json
```

## 1.1. Сводная таблица endpoint-ов

| Метод | Endpoint | Назначение | MVP |
|---|---|---|---|
| `GET` | `/health` | Проверить, что сервис жив | Да |
| `POST` | `/documents` | Загрузить учебный материал | Да |
| `GET` | `/documents` | Получить список документов | Позже |
| `GET` | `/documents/{document_id}` | Получить информацию о документе | Позже |
| `POST` | `/documents/{document_id}/index` | Запустить индексацию документа | Да |
| `GET` | `/jobs/{job_id}` | Проверить статус фоновой задачи | Позже |
| `POST` | `/search` | Найти релевантные фрагменты | Да |
| `POST` | `/answer` | Получить ответ ассистента | Да |
| `POST` | `/feedback` | Сохранить оценку ответа | Позже |

---

## 1.2. Минимальный MVP

Для первой версии достаточно реализовать:

| Порядок | Endpoint | Что должен делать |
|---:|---|---|
| 1 | `GET /health` | Возвращать статус сервиса |
| 2 | `POST /documents` | Принимать документ и сохранять его |
| 3 | `POST /documents/{document_id}/index` | Делить документ на chunks и сохранять embeddings |
| 4 | `POST /search` | Искать релевантные chunks |
| 5 | `POST /answer` | Возвращать ответ по найденным источникам |

`chunk` — фрагмент текста.  
`embedding` — векторное представление текста.  
`retrieval` — первичный поиск релевантных фрагментов.  
`reranker` — модель, которая повторно ранжирует найденные фрагменты.  
`confidence` — оценка уверенности ответа.  
`threshold` — порог, ниже которого система не должна уверенно отвечать.

---

## 1.3. Основной pipeline

```text
question
→ query embedding
→ vector search
→ top_k chunks
→ reranker
→ threshold filtering
→ prompt construction
→ LLM answer
→ structured response
→ sources
→ feedback logging
```

---

# 2. Подробная спецификация

---

# 2.1. Healthcheck

## `GET /api/v1/health`

Проверяет, что backend работает.

### Response `200 OK`

```json
{
  "status": "ok",
  "service": "medical-study-assistant",
  "version": "0.1.0"
}
```

---

# 2.2. Документы

---

## 2.2.1. Загрузить документ

## `POST /api/v1/documents`

Загружает учебный материал в систему.

На первом этапе лучше принимать текст напрямую через поле `text`.  
PDF/DOCX-загрузку можно добавить позже отдельным file upload endpoint-ом.

### Request body

```json
{
  "title": "Лекция по артериальной гипертензии",
  "source_type": "lecture",
  "specialty": "cardiology",
  "language": "ru",
  "text": "Полный текст учебного материала..."
}
```

### Request fields

| Поле | Тип | Обязательно | Комментарий |
|---|---|---:|---|
| `title` | `string` | Да | Название материала |
| `source_type` | `string` | Да | Тип источника |
| `specialty` | `string` | Нет | Направление: `cardiology`, `neurology`, etc. |
| `language` | `string` | Да | Язык материала: `ru`, `en` |
| `text` | `string` | Да | Полный текст документа |

### Возможные значения `source_type`

```text
lecture
guideline
book
article
notes
other
```

### Response `201 Created`

```json
{
  "document_id": "doc_123",
  "status": "uploaded"
}
```

---

## 2.2.2. Получить список документов

## `GET /api/v1/documents`

Возвращает список загруженных документов.

### Response `200 OK`

```json
{
  "documents": [
    {
      "document_id": "doc_123",
      "title": "Лекция по артериальной гипертензии",
      "source_type": "lecture",
      "specialty": "cardiology",
      "language": "ru",
      "status": "indexed",
      "chunks_count": 42,
      "created_at": "2026-07-09T19:10:00Z"
    }
  ]
}
```

### Document fields

| Поле | Тип | Комментарий |
|---|---|---|
| `document_id` | `string` | ID документа |
| `title` | `string` | Название |
| `source_type` | `string` | Тип источника |
| `specialty` | `string/null` | Медицинская специальность |
| `language` | `string` | Язык |
| `status` | `string` | Статус документа |
| `chunks_count` | `integer` | Количество фрагментов |
| `created_at` | `string` | Дата создания в ISO 8601 |

### Возможные значения `status`

```text
uploaded
indexing
indexed
failed
```

---

## 2.2.3. Получить документ

## `GET /api/v1/documents/{document_id}`

Возвращает информацию об одном документе.

### Path parameters

| Параметр | Тип | Комментарий |
|---|---|---|
| `document_id` | `string` | ID документа |

### Response `200 OK`

```json
{
  "document_id": "doc_123",
  "title": "Лекция по артериальной гипертензии",
  "source_type": "lecture",
  "specialty": "cardiology",
  "language": "ru",
  "status": "indexed",
  "chunks_count": 42,
  "created_at": "2026-07-09T19:10:00Z"
}
```

---

# 2.3. Индексация

---

## 2.3.1. Запустить индексацию документа

## `POST /api/v1/documents/{document_id}/index`

Запускает индексацию документа:

```text
document text
→ text cleaning
→ chunking
→ embedding calculation
→ vector DB insert
```

`chunking` — разбиение текста на фрагменты.  
`chunk_size` — размер одного фрагмента.  
`chunk_overlap` — пересечение соседних фрагментов, чтобы не потерять смысл на границах.

### Path parameters

| Параметр | Тип | Комментарий |
|---|---|---|
| `document_id` | `string` | ID документа |

### Request body

```json
{
  "chunk_size": 400,
  "chunk_overlap": 80
}
```

### Request fields

| Поле | Тип | Обязательно | Комментарий |
|---|---|---:|---|
| `chunk_size` | `integer` | Нет | Размер одного chunk-а |
| `chunk_overlap` | `integer` | Нет | Пересечение между соседними chunk-ами |

### Response `202 Accepted`

```json
{
  "document_id": "doc_123",
  "status": "indexing_started",
  "job_id": "job_456"
}
```

---

## 2.3.2. Проверить статус задачи

## `GET /api/v1/jobs/{job_id}`

Нужно, если индексация выполняется асинхронно.

### Path parameters

| Параметр | Тип | Комментарий |
|---|---|---|
| `job_id` | `string` | ID фоновой задачи |

### Response `200 OK`

```json
{
  "job_id": "job_456",
  "status": "completed",
  "progress": 100,
  "result": {
    "document_id": "doc_123",
    "chunks_count": 42
  }
}
```

### Возможные значения `status`

```text
pending
running
completed
failed
```

---

# 2.4. Поиск релевантных фрагментов

---

## 2.4.1. Semantic search

## `POST /api/v1/search`

Ищет фрагменты, которые семантически похожи на вопрос пользователя.

`semantic search` — смысловой поиск, а не простой поиск по совпадению слов.  
`top_k` — сколько лучших результатов вернуть.  
`score` — оценка релевантности.  
`retrieval_score` — score после первичного поиска.  
`rerank_score` — score после reranker-модели.

### Request body

```json
{
  "query": "Какие препараты применяются при артериальной гипертензии?",
  "top_k": 10,
  "filters": {
    "specialty": "cardiology",
    "source_type": ["lecture", "guideline"],
    "language": "ru"
  },
  "use_reranker": true
}
```

### Request fields

| Поле | Тип | Обязательно | Комментарий |
|---|---|---:|---|
| `query` | `string` | Да | Вопрос или поисковый запрос |
| `top_k` | `integer` | Нет | Количество результатов |
| `filters` | `object` | Нет | Фильтры по документам |
| `use_reranker` | `boolean` | Нет | Использовать ли reranker |

### Filters

| Поле | Тип | Комментарий |
|---|---|---|
| `specialty` | `string` | Медицинская специальность |
| `source_type` | `array[string]` | Типы источников |
| `language` | `string` | Язык документов |

### Response `200 OK`

```json
{
  "query": "Какие препараты применяются при артериальной гипертензии?",
  "results": [
    {
      "chunk_id": "chunk_001",
      "document_id": "doc_123",
      "document_title": "Лекция по артериальной гипертензии",
      "text": "Для лечения артериальной гипертензии применяются ингибиторы АПФ, БРА, диуретики...",
      "retrieval_score": 0.78,
      "rerank_score": 0.91,
      "page": 12,
      "section": "Лечение"
    }
  ]
}
```

### Result fields

| Поле | Тип | Комментарий |
|---|---|---|
| `chunk_id` | `string` | ID фрагмента |
| `document_id` | `string` | ID документа |
| `document_title` | `string` | Название документа |
| `text` | `string` | Текст найденного фрагмента |
| `retrieval_score` | `float` | Score первичного поиска |
| `rerank_score` | `float/null` | Score после reranker-а |
| `page` | `integer/null` | Страница, если источник PDF |
| `section` | `string/null` | Раздел документа |

---

# 2.5. Генерация ответа

---

## 2.5.1. Получить ответ ассистента

## `POST /api/v1/answer`

Главный endpoint MVP.

Он должен:

```text
1. принять вопрос
2. найти релевантные chunks
3. отранжировать chunks через reranker
4. отфильтровать слабые источники по threshold
5. собрать prompt
6. получить ответ от LLM
7. вернуть ответ в строгом формате
```

`answer` — ответ.  
`evidence` — доказательства/источники.  
`sources` — источники, на которых основан ответ.  
`strict_sources` — режим, при котором модель должна отвечать только по найденным материалам.

### Request body

```json
{
  "question": "Какие основные группы препаратов применяются при артериальной гипертензии?",
  "mode": "study",
  "top_k": 10,
  "filters": {
    "specialty": "cardiology",
    "source_type": ["lecture", "guideline"],
    "language": "ru"
  },
  "strict_sources": true
}
```

### Request fields

| Поле | Тип | Обязательно | Комментарий |
|---|---|---:|---|
| `question` | `string` | Да | Вопрос пользователя |
| `mode` | `string` | Нет | Режим ответа |
| `top_k` | `integer` | Нет | Сколько фрагментов искать |
| `filters` | `object` | Нет | Фильтры по документам |
| `strict_sources` | `boolean` | Да | Отвечать только по источникам |

### Возможные значения `mode`

```text
study
summary
exam
clinical_reference
```

### Response `200 OK`

```json
{
  "answer_id": "ans_789",
  "question": "Какие основные группы препаратов применяются при артериальной гипертензии?",
  "answer": {
    "short_answer": "Основные группы препаратов: ингибиторы АПФ, блокаторы рецепторов ангиотензина II, диуретики, блокаторы кальциевых каналов и бета-блокаторы.",
    "detailed_answer": "В учебных материалах указано, что терапия артериальной гипертензии может включать несколько основных классов препаратов: ингибиторы АПФ, БРА, тиазидные и тиазидоподобные диуретики, блокаторы кальциевых каналов и бета-блокаторы. Выбор конкретной группы зависит от сопутствующих заболеваний, переносимости и клинического контекста.",
    "limitations": "Ответ основан только на загруженных учебных материалах и не является индивидуальной клинической рекомендацией."
  },
  "sources": [
    {
      "source_id": "src_001",
      "chunk_id": "chunk_001",
      "document_id": "doc_123",
      "document_title": "Лекция по артериальной гипертензии",
      "page": 12,
      "section": "Лечение",
      "quote": "Для лечения артериальной гипертензии применяются ингибиторы АПФ, БРА, диуретики...",
      "rerank_score": 0.91
    }
  ],
  "confidence": {
    "level": "high",
    "score": 0.86,
    "reason": "Найдено несколько релевантных фрагментов с высоким rerank_score."
  },
  "safety": {
    "is_medical": true,
    "requires_doctor_review": true,
    "disclaimer": "Информация предназначена для обучения и не заменяет решение врача."
  }
}
```

### Answer fields

| Поле | Тип | Комментарий |
|---|---|---|
| `answer_id` | `string` | ID ответа |
| `question` | `string` | Исходный вопрос |
| `answer.short_answer` | `string` | Краткий ответ |
| `answer.detailed_answer` | `string` | Подробный ответ |
| `answer.limitations` | `string` | Ограничения ответа |
| `sources` | `array` | Источники |
| `confidence` | `object` | Уверенность системы |
| `safety` | `object` | Медицинские ограничения |

### Confidence levels

```text
high
medium
low
insufficient_sources
```

### Пример отказа из-за слабых источников

Если релевантных фрагментов недостаточно:

```json
{
  "answer_id": "ans_790",
  "question": "Как лечить редкое осложнение X?",
  "answer": {
    "short_answer": "В загруженных материалах недостаточно информации для ответа.",
    "detailed_answer": "Я не нашёл достаточно релевантных фрагментов в доступных учебных материалах. Поэтому корректный ответ по источникам сформировать нельзя.",
    "limitations": "Ответ не должен использоваться как клиническая рекомендация."
  },
  "sources": [],
  "confidence": {
    "level": "insufficient_sources",
    "score": 0.12,
    "reason": "Лучший найденный фрагмент ниже порога релевантности."
  },
  "safety": {
    "is_medical": true,
    "requires_doctor_review": true,
    "disclaimer": "Информация предназначена для обучения и не заменяет решение врача."
  }
}
```

---

# 2.6. Feedback

---

## 2.6.1. Оценить ответ

## `POST /api/v1/feedback`

Сохраняет пользовательскую оценку ответа.

Это нужно для будущей аналитики качества:

```text
какие ответы полезны
какие ответы ошибочны
на каких темах RAG плохо ищет источники
какие документы дают плохие chunks
```

### Request body

```json
{
  "answer_id": "ans_789",
  "rating": 4,
  "is_correct": true,
  "comment": "Ответ полезный, но хотелось бы больше про противопоказания."
}
```

### Request fields

| Поле | Тип | Обязательно | Комментарий |
|---|---|---:|---|
| `answer_id` | `string` | Да | ID ответа |
| `rating` | `integer` | Нет | Оценка, например от 1 до 5 |
| `is_correct` | `boolean` | Нет | Пользователь считает ответ корректным или нет |
| `comment` | `string` | Нет | Свободный комментарий |

### Response `201 Created`

```json
{
  "status": "saved"
}
```

---

# 2.7. Ошибки

---

## 2.7.1. Общий формат ошибки

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document with id doc_123 was not found."
  }
}
```

---

## 2.7.2. Таблица ошибок

| HTTP status | Code | Когда |
|---:|---|---|
| `400` | `BAD_REQUEST` | Неправильный запрос |
| `404` | `DOCUMENT_NOT_FOUND` | Документ не найден |
| `404` | `JOB_NOT_FOUND` | Задача не найдена |
| `422` | `VALIDATION_ERROR` | Не прошла валидация |
| `500` | `INTERNAL_ERROR` | Внутренняя ошибка |
| `503` | `MODEL_UNAVAILABLE` | Модель недоступна |
| `503` | `VECTOR_DB_UNAVAILABLE` | Vector DB недоступна |

---

# 3. Рекомендуемые Pydantic-схемы

`Pydantic` нужен для валидации данных.  
`Field` — поле модели с ограничениями.  
`ge` = `greater or equal`, больше или равно.  
`le` = `less or equal`, меньше или равно.

```python
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class DocumentCreateRequest(BaseModel):
    title: str
    source_type: str
    specialty: Optional[str] = None
    language: str = "ru"
    text: str


class DocumentCreateResponse(BaseModel):
    document_id: str
    status: str


class DocumentItem(BaseModel):
    document_id: str
    title: str
    source_type: str
    specialty: Optional[str] = None
    language: str
    status: str
    chunks_count: int = 0
    created_at: str


class DocumentsListResponse(BaseModel):
    documents: List[DocumentItem]


class IndexDocumentRequest(BaseModel):
    chunk_size: int = Field(default=400, ge=100, le=3000)
    chunk_overlap: int = Field(default=80, ge=0, le=1000)


class IndexDocumentResponse(BaseModel):
    document_id: str
    status: str
    job_id: str


class SearchFilters(BaseModel):
    specialty: Optional[str] = None
    source_type: Optional[List[str]] = None
    language: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=30)
    filters: Optional[SearchFilters] = None
    use_reranker: bool = True


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    retrieval_score: float
    rerank_score: Optional[float] = None
    page: Optional[int] = None
    section: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]


class AnswerRequest(BaseModel):
    question: str
    mode: str = "study"
    top_k: int = Field(default=10, ge=1, le=30)
    filters: Optional[SearchFilters] = None
    strict_sources: bool = True


class AnswerBody(BaseModel):
    short_answer: str
    detailed_answer: str
    limitations: str


class SourceItem(BaseModel):
    source_id: str
    chunk_id: str
    document_id: str
    document_title: str
    page: Optional[int] = None
    section: Optional[str] = None
    quote: str
    rerank_score: Optional[float] = None


class Confidence(BaseModel):
    level: str
    score: float
    reason: str


class SafetyBlock(BaseModel):
    is_medical: bool
    requires_doctor_review: bool
    disclaimer: str


class AnswerResponse(BaseModel):
    answer_id: str
    question: str
    answer: AnswerBody
    sources: List[SourceItem]
    confidence: Confidence
    safety: SafetyBlock


class FeedbackRequest(BaseModel):
    answer_id: str
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    is_correct: Optional[bool] = None
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
```

---

# 4. Рекомендуемый порядок написания кода

## 4.1. Структура проекта

```text
app/
  main.py
  schemas.py
  config.py

  api/
    routes_health.py
    routes_documents.py
    routes_search.py
    routes_answer.py
    routes_feedback.py

  services/
    document_service.py
    chunking_service.py
    embedding_service.py
    retrieval_service.py
    rerank_service.py
    answer_service.py
    feedback_service.py

  repositories/
    document_repository.py
    vector_repository.py
    feedback_repository.py

  models/
    document.py
    chunk.py
    feedback.py
```

---

## 4.2. Первый этап

Сначала сделать API без настоящего ML:

```text
1. FastAPI app
2. Pydantic schemas
3. in-memory document storage
4. mock indexing
5. mock search
6. mock answer
```

Так ты сначала проверишь контракт, а не утонешь в Qdrant, embeddings и LLM.

---

## 4.3. Второй этап

Подключить реальный RAG:

```text
1. chunking_service
2. embedding_service
3. vector_repository
4. retrieval_service
5. rerank_service
6. answer_service
```

---

## 4.4. Третий этап

Добавить качество и безопасность:

```text
1. thresholds
2. insufficient_sources fallback
3. source quotes
4. feedback logging
5. evaluation dataset
6. answer quality metrics
```

---

# 5. Главная рекомендация

Главный endpoint проекта:

```http
POST /api/v1/answer
```

Именно его стоит считать продуктовым API.

Внутри него должен быть pipeline:

```text
question
→ embedding
→ vector search
→ reranker
→ threshold
→ LLM answer
→ sources
→ confidence
→ safety
→ structured response
```

Для первой версии не нужно пытаться сделать всё идеально.  
Нужно добиться, чтобы система стабильно проходила такой сценарий:

```text
загрузил текст
→ проиндексировал
→ задал вопрос
→ получил ответ с источниками
```
