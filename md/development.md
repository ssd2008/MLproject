# Локальная разработка

Этот режим предназначен для изменения backend или frontend. Для обычного использования проекта лучше запускать весь стек через [Docker Compose](start.md).

## Стек

- Python 3.11+;
- FastAPI и Uvicorn;
- PostgreSQL 16;
- Qdrant 1.14.1;
- Node.js 22 и npm для frontend;
- Docker Compose для инфраструктуры;
- pytest и Ruff для проверок.

`Uvicorn` — ASGI-сервер. `ASGI` расшифровывается как Asynchronous Server Gateway Interface: асинхронный интерфейс между Python web-приложением и сервером.

## Backend: лёгкий режим

Лёгкий режим не загружает Sentence Transformers и Whisper. Он удобен для разработки API, CI и запуска unit-тестов.

### 1. Создай виртуальное окружение

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

Если PowerShell запрещает запуск скрипта активации:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

### 2. Установи зависимости

Воспроизводимый вариант с закреплёнными версиями:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.lock.txt
```

Файл `requirements-dev.txt` содержит допустимые диапазоны прямых зависимостей. `requirements-dev.lock.txt` фиксирует проверенный набор версий для разработки и CI.

### 3. Создай `.env`

macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Для лёгкого режима измени:

```dotenv
EMBEDDING_BACKEND=hash
RERANKER_ENABLED=false
RERANKER_BACKEND=lexical
ASR_BACKEND=disabled
QDRANT_COLLECTION_NAME=document_chunks_v1
```

`backend` означает реализацию внутреннего механизма. `hash` использует детерминированные псевдоэмбеддинги, а `lexical` остаётся доступной тестовой реализацией reranker. При `RERANKER_ENABLED=false` reranker не вызывается. Этот режим нужен для разработки, но не отражает качество реального семантического поиска.

### 4. Запусти инфраструктуру

```bash
docker compose up -d postgres qdrant
```

PostgreSQL и Qdrant публикуются только на `127.0.0.1`.

### 5. Примени миграции

```bash
python -m scripts.migrate
```

Скрипты запускаются через `python -m scripts.<name>`, чтобы корень проекта находился в Python import path и пакет `app` корректно импортировался.

### 6. Запусти API

```bash
uvicorn app.main:app --reload
```

`--reload` означает автоматическую перезагрузку процесса при изменении исходных файлов.

API:

- `http://127.0.0.1:8000`;
- Swagger UI: `http://127.0.0.1:8000/docs`;
- healthcheck: `http://127.0.0.1:8000/api/v1/health`.

## Backend: полноценный ML-режим

Для локальной установки:

```bash
python -m pip install -r requirements-ml.txt
```

Для проверки Docker-совместимого набора прямых ML-зависимостей:

```bash
python -m pip install -r requirements-ml.lock.txt
```

В `.env`:

```dotenv
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-large
EMBEDDING_DIMENSION=1024
EMBEDDING_DEVICE=auto

RERANKER_ENABLED=false
RERANKER_BACKEND=cross-encoder
RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
RERANKER_DEVICE=auto

ASR_BACKEND=faster-whisper
ASR_MODEL_NAME=small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8

QDRANT_COLLECTION_NAME=document_chunks_e5_large_v1
```

Основной ML-режим использует только Dense retrieval. Это решение принято по результатам benchmark: Dense получил `MRR=0.865`, `Top-1 gold accuracy=78.3%` и `Recall@5=0.983` при медианной задержке `0.297` секунды.

Скачать включённые модели заранее:

```bash
python -m scripts.download_models
```

При `RERANKER_ENABLED=false` скрипт скачивает embedding- и ASR-модели и выводит:

```text
Skipping reranker model: RERANKER_ENABLED=false
```

`dimension` — размерность, то есть число компонентов embedding-вектора. При смене embedding-модели или размерности используй новое имя Qdrant collection, иначе в коллекции могут оказаться несовместимые векторы.

Docker image отдельно устанавливает CPU-сборку PyTorch. Это не добавляет CUDA/NVIDIA runtime в стандартный `amd64` image и заметно уменьшает его размер.

## Экспериментальный reranker

Reranker сохранён для дальнейших исследований, но не входит в стандартный pipeline.

Чтобы разрешить его глобально:

```dotenv
RERANKER_ENABLED=true
```

После изменения флага повторно запусти загрузку моделей:

```bash
python -m scripts.download_models
```

Для отдельного запроса укажи:

```json
{
  "use_reranker": true
}
```

Reranking выполняется только при одновременном выполнении двух условий:

1. `RERANKER_ENABLED=true` в конфигурации сервера;
2. `use_reranker=true` в запросе.

При выключенном глобальном флаге запрос выполняется через Dense retrieval, а `rerank_score` остаётся `null`.

В текущем эксперименте reranker повысил Recall@5 только с `0.983` до `1.000`, но снизил MRR до `0.715`, снизил Top-1 gold accuracy до `58.3%` и увеличил p50 latency до `5.525` секунды. Поэтому включение оправдано только для повторных экспериментов на новых данных.

Подробности: [retrieval benchmark](../evaluation/README.md) и [результаты](../evaluation/RESULTS.md).

## Frontend

Версии frontend-зависимостей закреплены в `frontend/package.json` и `frontend/package-lock.json`.

```bash
cd frontend
npm ci --no-audit --no-fund
npm run dev
```

`npm ci` устанавливает строго тот набор пакетов, который записан в lock-файле. После намеренного изменения зависимостей выполни `npm install`, проверь обновлённый `package-lock.json` и закоммить оба файла.

Vite dev server по умолчанию доступен на:

```text
http://127.0.0.1:5173
```

Production build:

```bash
npm run build
```

TypeScript-проверка:

```bash
npm run lint
```

## Проверки

Backend:

```bash
ruff check .
python -m pytest
```

Проверка Compose-файла:

```bash
docker compose config --quiet
```

Smoke test уже запущенного API:

```bash
python -m scripts.smoke_test
```

`smoke test` — короткая сквозная проверка основного сценария: healthcheck, создание документа, индексация и получение ответа. Тест удаляет созданный документ в конце и завершается ошибкой, если indexing job не выполнен. По умолчанию smoke test проверяет Dense retrieval.

Retrieval benchmark без reranker:

```bash
docker compose -f evaluation/docker-compose.yml run --rm benchmark
```

Повтор полного сравнения:

```bash
docker compose -f evaluation/docker-compose.yml run --rm benchmark \
  bash -lc "python -m evaluation.prepare_dataset --questions 60 && \
  python -m evaluation.run_benchmark --device cpu --include-bm25 --with-reranker"
```

## Полезные команды Docker

```bash
docker compose ps --all
docker compose logs -f postgres qdrant
docker compose restart postgres qdrant
docker compose down
```

Удалить только локальные данные инфраструктуры:

```bash
docker compose down -v
```

> Команда с `-v` необратимо удаляет Docker volumes.

## CI

GitHub Actions выполняет:

1. `docker compose config --quiet`;
2. Ruff и pytest;
3. lightweight integration test с PostgreSQL и Qdrant;
4. frontend `npm ci` и production build;
5. отдельную проверку подготовки retrieval dataset и evaluation unit-тестов.

Полный тяжёлый ML image и полный model benchmark в CI не запускаются на каждый commit.

## Переменные окружения

| Префикс | Назначение |
|---|---|
| `DATABASE_` | PostgreSQL и connection pool |
| `QDRANT_` | адрес, коллекция и batch upsert |
| `EMBEDDING_` | embedding backend и модель |
| `RERANKER_` | глобальный флаг, backend и optional reranker-модель |
| `ASR_` | распознавание речи |
| `ANSWER_` | extractive или внешний генеративный ответ |
| `CHUNK_` | размер и overlap текстовых чанков |
| `VIDEO_` | длительность и overlap видео-чанков |
| `MAX_` | ограничения размера загрузок |

Полный список значений находится в `.env.example` и `app/config.py`.
