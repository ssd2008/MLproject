# Асси — Medical Learning Assistant

Асси — ИИ-ассистент для врачей и ординаторов, который помогает находить, изучать и применять информацию из загруженных учебных медицинских материалов.

Проект принимает текст, веб-страницы, PDF и видео лекций, индексирует их содержимое и возвращает релевантные фрагменты либо ответы с привязкой к исходным страницам и тайм-кодам.

> **Статус:** рабочий MVP для обучения и демонстрации. Асси не предназначен для автономной постановки диагноза, назначения лечения или замены клинического решения врача.

<!-- TODO: вставить общий скрин интерфейса Асси -->

## Решаемая проблема

Учебные материалы часто распределены между длинными лекциями, PDF-презентациями, конспектами и веб-страницами. Обычный поиск работает только по точному совпадению слов и не связывает формулировку вопроса с семантически близкими фрагментами.

Асси строит единый поисковый слой поверх загруженных источников:

1. извлекает текст или транскрибирует речь;
2. разбивает материал на связанные фрагменты;
3. строит embedding-векторы;
4. сохраняет векторы и metadata в Qdrant;
5. находит кандидатов по смысловой близости;
6. повторно ранжирует их cross-encoder-моделью;
7. формирует ответ и цитаты.

## Основной сценарий

```text
Загрузка источника
  -> извлечение текста или ASR
  -> chunking
  -> embeddings
  -> Qdrant
  -> semantic retrieval
  -> reranking
  -> ответ с citations
```

`chunking` — разбиение материала на чанки, то есть небольшие фрагменты с overlap. `overlap` — перекрытие соседних фрагментов, которое уменьшает потерю контекста на границах.

`embedding` — числовой вектор, описывающий смысл текста. `dimension` — размерность, то есть количество чисел в таком векторе.

`reranking` — повторное ранжирование уже найденных кандидатов более точной, но более дорогой моделью.

## Поддерживаемые источники

| Источник | Обработка | Привязка результата |
|---|---|---|
| Текст | Сохраняется и разбивается на чанки | Символьные позиции |
| URL | Backend загружает и извлекает текст страницы | URL и символьные позиции |
| PDF | Извлекается текстовый слой | Страницы и символьные позиции |
| Видео | Локальная транскрибация через `faster-whisper` | Тайм-коды и символьные позиции |

Для URL применяется защита от SSRF: обращения к private, loopback и link-local адресам запрещаются.

PDF без текстового слоя не распознаются, поскольку OCR пока не входит в MVP.

Видео поддерживает локальное распознавание речи и word-level timestamps — временные метки отдельных слов.

## Поиск

### Retriever

Retriever использует модель:

```text
intfloat/multilingual-e5-large
```

Она преобразует вопрос и чанки в векторы размерности 1024. Qdrant выполняет dense semantic search и возвращает `candidate_k` ближайших фрагментов.

`candidate_k` — размер пула кандидатов. Он должен быть не меньше `top_k`.

### Reranker

Reranker использует cross-encoder:

```text
BAAI/bge-reranker-v2-m3
```

Cross-encoder получает вопрос и текст кандидата одновременно, поэтому оценивает их совместную релевантность точнее, чем косинусное сходство отдельных embeddings.

Итоговый score:

```text
normalized_retrieval_score = clamp((retrieval_score + 1) / 2, 0, 1)

final_score =
    normalized_retrieval_score,                         без reranker
    0.25 * normalized_retrieval_score
      + 0.75 * rerank_score,                            с reranker
```

`score` здесь является внутренним ранжирующим показателем, а не калиброванной вероятностью правильности.

### Контекст видео

Видео разбивается на окна длительностью до 20 секунд с overlap 2 секунды. Поиск и reranker оценивают центральные чанки. После ранжирования к выбранному видео-фрагменту добавляются соседние чанки, а пересекающийся текст дедуплицируется.

```text
20-second chunks
  -> dense retrieval
  -> cross-encoder reranking
  -> central hits
  -> previous + central + next chunk
  -> merge without duplicated overlap
```

Это сохраняет точность поиска и возвращает более связный фрагмент с диапазоном времени.

<!-- TODO: вставить скрин результата поиска по видео с тайм-кодом -->

## Ответы

Endpoint ответа использует результаты поиска и возвращает:

- текст ответа;
- citations — цитаты с координатами источника;
- confidence в диапазоне `[0, 1]`;
- limitations — ограничения конкретного ответа;
- safety notes;
- количество использованных чанков;
- время обработки.

По умолчанию используется `extractive` backend: ответ составляется локально из найденных фрагментов без внешней LLM.

Опционально поддерживается OpenAI backend. Если внешний provider недоступен, сервис возвращает extractive fallback и фиксирует ограничение в `limitations`.

## Архитектура приложения

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

Разделение ответственности:

- `router` принимает HTTP-запрос и вызывает сервис;
- `service` содержит бизнес-логику;
- `repository` отвечает за чтение и запись данных;
- `schema` описывает и валидирует входные и выходные структуры;
- `provider` инкапсулирует конкретную модель или внешнюю систему.

## Хранилища

### PostgreSQL

Хранит:

- документы и metadata;
- статусы документов;
- indexing jobs;
- progress и ошибки фоновых заданий;
- feedback пользователей.

### Qdrant

Хранит:

- чанки;
- dense vectors;
- координаты страниц и тайм-кодов;
- metadata для фильтрации;
- идентификаторы документов.

### Docker volumes

Docker Compose создаёт постоянные volumes для:

- PostgreSQL;
- Qdrant;
- загруженных файлов;
- Hugging Face cache.

Обычный `docker compose down` не удаляет данные. Команда `docker compose down -v` удаляет их.

## API

Base path:

```text
/api/v1
```

Основные endpoint-ы:

| Method | Endpoint | Назначение |
|---|---|---|
| `GET` | `/health` | Состояние компонентов |
| `POST` | `/documents` | Создать text- или URL-документ |
| `POST` | `/documents/upload` | Загрузить PDF |
| `POST` | `/documents/upload/video` | Загрузить видео |
| `GET` | `/documents` | Получить список документов |
| `GET` | `/documents/{document_id}` | Получить документ |
| `DELETE` | `/documents/{document_id}` | Удалить документ |
| `POST` | `/documents/{document_id}/index` | Запустить индексацию |
| `GET` | `/jobs/{job_id}` | Получить состояние задания |
| `POST` | `/search` | Найти релевантные фрагменты |
| `POST` | `/answer` | Получить ответ с цитатами |
| `POST` | `/feedback` | Сохранить оценку ответа |

Подробности: [API-спецификация](api_spec.md).

## Конфигурация по умолчанию

Docker Compose запускает:

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

Облегчённый режим для тестов и разработки:

```dotenv
EMBEDDING_BACKEND=hash
RERANKER_BACKEND=lexical
ASR_BACKEND=disabled
QDRANT_COLLECTION_NAME=document_chunks_v1
```

## Ограничения MVP

- PDF-сканы без текстового слоя требуют внешнего OCR;
- файлы при загрузке пока читаются в память целиком;
- indexing jobs выполняются внутри процесса FastAPI и не переживают его перезапуск;
- локальное файловое хранилище не подходит для горизонтального масштабирования;
- нет authentication, authorization и пользовательской изоляции;
- нет rate limiting и ресурсных квот;
- нет speaker diarization;
- нет hybrid dense+sparse retrieval;
- нет production evaluation dataset и автоматического контроля качества;
- Docker Compose ориентирован на локальный запуск, а не production deployment.

## Запуск и разработка

- [Быстрый запуск](start.md);
- [Установка на macOS](install_macos.md);
- [Установка на Windows](install_windows.md);
- [Локальная разработка](development.md);
- [Типовые проблемы](troubleshooting.md).

## Safety

Асси работает с учебными материалами. Ответы нужно проверять по первичным источникам и цитатам. Проект не заменяет врача и не должен использоваться как самостоятельная диагностическая или лечебная система.
