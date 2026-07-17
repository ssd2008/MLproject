# Асси — Medical Learning Assistant

Асси — ИИ-ассистент для врачей и ординаторов, который помогает находить, изучать и применять информацию из загруженных учебных медицинских материалов.

Проект принимает текст, веб-страницы, PDF и видео лекций, индексирует содержимое и возвращает релевантные фрагменты либо ответы с привязкой к страницам и тайм-кодам.

> **Статус:** рабочий MVP для обучения и демонстрации. Асси не предназначен для автономной постановки диагноза, назначения лечения или замены клинического решения врача.

<!-- TODO: вставить общий скрин интерфейса Асси -->

## Решаемая проблема

Учебные материалы часто распределены между длинными лекциями, PDF-презентациями, конспектами и веб-страницами. Асси строит единый поисковый слой поверх загруженных источников:

1. извлекает текст или транскрибирует речь;
2. разбивает материал на чанки с overlap;
3. строит embedding-векторы;
4. сохраняет векторы и metadata в Qdrant;
5. находит кандидатов по смысловой близости;
6. повторно ранжирует их cross-encoder-моделью;
7. формирует ответ и цитаты.

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

`chunking` — разбиение материала на небольшие фрагменты. `overlap` — перекрытие соседних фрагментов, уменьшающее потерю контекста на границах.

`embedding` — числовой вектор, описывающий смысл текста. `dimension` — количество чисел в этом векторе.

`reranking` — повторное ранжирование найденных кандидатов более точной моделью.

## Поддерживаемые источники

| Источник | Обработка | Привязка результата |
|---|---|---|
| Текст | Сохраняется и разбивается на чанки | Символьные позиции |
| URL | Загружается и очищается текст страницы | URL и символьные позиции |
| PDF | Извлекается текстовый слой | Страницы и символьные позиции |
| Видео | Локальная транскрибация через `faster-whisper` | Тайм-коды и символьные позиции |

URL-загрузка ограничена публичными HTTP(S)-адресами. Каждый redirect проверяется до следующего запроса; локальные и специальные IP-диапазоны запрещены. Proxy-переменные окружения не используются, а доступный transport peer address сверяется с DNS-результатом.

PDF без текстового слоя не распознаются, поскольку OCR пока не входит в MVP.

## Поиск

### Retriever

```text
intfloat/multilingual-e5-large
```

Модель преобразует вопрос и чанки в векторы размерности 1024. Qdrant выполняет dense semantic search и возвращает `candidate_k` ближайших фрагментов.

### Reranker

```text
BAAI/bge-reranker-v2-m3
```

Cross-encoder получает вопрос и текст кандидата одновременно и оценивает их совместную релевантность.

```text
normalized_retrieval_score = clamp((retrieval_score + 1) / 2, 0, 1)

final_score =
    normalized_retrieval_score,                         без reranker
    0.25 * normalized_retrieval_score
      + 0.75 * rerank_score,                            с reranker
```

`score` является внутренним ранжирующим показателем, а не калиброванной вероятностью правильности.

### Контекст видео

Видео разбивается на окна длительностью до 20 секунд с overlap 2 секунды. После ранжирования к выбранному фрагменту добавляются соседние чанки, а пересекающийся текст дедуплицируется.

<!-- TODO: вставить скрин результата поиска по видео с тайм-кодом -->

## Ответы

Endpoint ответа возвращает:

- текст ответа;
- citations с координатами источника;
- confidence в диапазоне `[0, 1]`;
- limitations;
- safety notes;
- количество использованных чанков;
- время обработки.

По умолчанию используется локальный `extractive` backend: ответ собирается из найденных фрагментов без внешней генеративной модели.

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

- `router` принимает HTTP-запрос;
- `service` содержит бизнес-логику;
- `repository` читает и записывает данные;
- `schema` валидирует входные и выходные структуры;
- `provider` инкапсулирует модель или внешнюю систему.

## Хранилища

PostgreSQL хранит документы, metadata, статусы, indexing jobs, progress, ошибки и feedback.

Qdrant хранит чанки, dense vectors, координаты страниц и тайм-кодов и metadata для фильтрации.

Docker Compose создаёт постоянные volumes для PostgreSQL, Qdrant, загруженных файлов и Hugging Face cache. Обычный `docker compose down` не удаляет данные, а `docker compose down -v` удаляет.

## Локальная сетевая модель

Compose публикует frontend, API, PostgreSQL и Qdrant только на `127.0.0.1`. Qdrant gRPC-порт наружу не публикуется.

Проект не рассчитан на прямое размещение в интернете: в MVP нет пользовательской аутентификации, изоляции и rate limiting.

## Healthcheck

`GET /api/v1/health` проверяет подключение к PostgreSQL и Qdrant. Для embedding, reranker, ASR и answer возвращается настроенная реализация с префиксом `configured:`. Healthcheck не загружает модели и не выполняет тестовый inference.

## API

Base path:

```text
/api/v1
```

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

Docker image использует CPU-only PyTorch. На `amd64` устанавливается CPU wheel, поэтому стандартная сборка не включает CUDA/NVIDIA runtime. На `arm64` используется обычная CPU-сборка PyTorch.

Закреплённые версии Python-зависимостей находятся в `requirements-runtime.lock.txt`, `requirements-dev.lock.txt` и `requirements-ml.lock.txt`. Прямые frontend-зависимости закреплены точными версиями в `frontend/package.json`.

## Облегчённый режим

```dotenv
EMBEDDING_BACKEND=hash
RERANKER_BACKEND=lexical
ASR_BACKEND=disabled
QDRANT_COLLECTION_NAME=document_chunks_v1
```

## Ограничения MVP

- PDF-сканы без текстового слоя требуют внешнего OCR;
- файлы при загрузке читаются в память целиком;
- indexing jobs выполняются внутри FastAPI и не переживают перезапуск;
- локальное файловое хранилище не подходит для горизонтального масштабирования;
- нет пользовательской аутентификации и изоляции;
- нет rate limiting и ресурсных квот;
- нет speaker diarization;
- нет hybrid dense+sparse retrieval;
- нет production evaluation dataset;
- Docker Compose предназначен для локального запуска.

## Документация

- [Быстрый запуск](start.md);
- [Установка на macOS](install_macos.md);
- [Установка на Windows](install_windows.md);
- [Локальная разработка](development.md);
- [Типовые проблемы](troubleshooting.md);
- [Security Policy](../SECURITY.md).

## Safety

Асси работает с учебными материалами. Ответы нужно проверять по первичным источникам и цитатам. Проект не заменяет врача и не должен использоваться как самостоятельная диагностическая или лечебная система.
