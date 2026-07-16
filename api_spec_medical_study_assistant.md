# API Spec v0.2 — Medical Learning Assistant

Base URL: `/api/v1`  
OpenAPI UI: `/docs`

The service is educational. It must not be treated as a diagnostic or treatment system.

## Error format

```json
{
  "code": "document_not_found",
  "detail": "Document not found",
  "context": {"document_id": "..."}
}
```

Validation errors use `code=validation_error` and HTTP 422.

## Health

### `GET /health`

Returns component status for PostgreSQL, Qdrant and active ML/provider backends. HTTP 503 is used when a required dependency is unavailable.

## Documents

### `POST /documents`

Creates a text or URL document. URL sources are downloaded by the backend; URLs resolving to private, loopback or link-local networks are rejected.

Text request:

```json
{
  "title": "Лекция по артериальной гипертензии",
  "source_type": "text",
  "raw_text": "Полный текст...",
  "specialty": "cardiology",
  "lecture_date": "2026-07-14",
  "language": "ru",
  "metadata": {}
}
```

URL request:

```json
{
  "title": "Материал курса",
  "source_type": "url",
  "source_url": "https://example.org/lecture",
  "language": "ru",
  "metadata": {}
}
```

Possible `source_type` values: `text`, `url`, `pdf`.

### `POST /documents/upload`

Multipart PDF upload.

Fields:

- `file`: PDF;
- `title`: required;
- `specialty`: optional;
- `language`: default `ru`;
- `lecture_date`: optional ISO date;
- `metadata`: optional JSON object encoded as a string.

PDF files without a text layer are rejected because OCR is not part of v0.2.

### `GET /documents`

Query parameters:

- `limit` — 1..500;
- `offset` — non-negative;
- `status` — `uploaded`, `processing`, `ready`, `failed`;
- `source_type`;
- `specialty`.

### `GET /documents/{document_id}`

Returns one document without the full source text.

### `DELETE /documents/{document_id}`

Deletes PostgreSQL metadata, local uploaded file and all Qdrant points of the document.

## Indexing

### `POST /documents/{document_id}/index`

Creates a background indexing job.

```json
{
  "chunk_size": 400,
  "chunk_overlap": 80
}
```

Both fields are optional. Response HTTP 202:

```json
{
  "document_id": "...",
  "job_id": "...",
  "status": "pending"
}
```

Pipeline:

```text
extracted text
-> deterministic chunks with overlap
-> document embeddings
-> delete previous document points
-> Qdrant upsert
-> document status ready
```

Point IDs are deterministic UUIDv5 values based on document ID, chunk index and SHA-256 content hash.

### `GET /jobs/{job_id}`

Returns `pending`, `running`, `completed` or `failed`, progress 0..100 and result/error fields.

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
    "source_types": ["text", "pdf"],
    "language": "ru",
    "lecture_date_from": null,
    "lecture_date_to": null
  }
}
```

`candidate_k` is the retriever pool size and must be at least `top_k`. Results contain retrieval, rerank and final scores plus source/page/character offsets.

When reranking is enabled:

```text
final_score = 0.25 * normalized_retrieval_score + 0.75 * rerank_score
```

This is an application ranking score, not a calibrated probability.

## Answer

### `POST /answer`

Uses the same search fields plus:

```json
{
  "max_context_chunks": 6,
  "response_style": "detailed",
  "include_citations": true
}
```

`response_style`: `brief`, `detailed`, `study_notes`.

Response:

- `answer`;
- `citations` with chunk and source coordinates;
- `confidence` heuristic in `[0, 1]`;
- `limitations`;
- `safety_notes`;
- `used_chunks`;
- `took_ms`.

If the OpenAI provider fails, the service returns an extractive fallback and records the limitation.

## Feedback

### `POST /feedback`

```json
{
  "query": "...",
  "answer": "...",
  "rating": 1,
  "comment": "Полезно",
  "document_ids": [],
  "metadata": {}
}
```

`rating` is `1` or `-1`.

## Storage model

PostgreSQL stores documents, indexing jobs and feedback. Qdrant stores chunks, dense vectors and retrieval payload. Full document text and internal file paths are not returned by normal document endpoints.
