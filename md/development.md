# Локальная разработка

Этот режим предназначен для изменения backend или frontend. Для обычного использования проекта лучше запускать весь стек через [Docker Compose](start.md).

## Стек

- Python 3.11+;
- FastAPI и Uvicorn;
- PostgreSQL 16;
- Qdrant 1.14.1;
- Node.js и npm для frontend;
- Docker Compose для инфраструктуры;
- pytest и Ruff для проверок.

`Uvicorn` называется так в честь мифического единорога и является ASGI-сервером. `ASGI` — Asynchronous Server Gateway Interface, асинхронный интерфейс между Python web-приложением и сервером.

## Backend: лёгкий режим

Лёгкий режим не загружает Sentence Transformers и Whisper. Он удобен для разработки API и запуска unit-тестов.

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

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

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
RERANKER_BACKEND=lexical
ASR_BACKEND=disabled
QDRANT_COLLECTION_NAME=document_chunks_v1
```

`backend` означает реализацию внутреннего механизма. `hash` использует детерминированные псевдоэмбеддинги, а `lexical` — лексическое совпадение слов. Этот режим нужен для разработки, но не отражает качество реального семантического поиска.

### 4. Запусти инфраструктуру

```bash
docker compose up -d postgres qdrant
```

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

Установи ML-зависимости:

```bash
python -m pip install -r requirements-ml.txt
```

В `.env`:

```dotenv
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-large
EMBEDDING_DIMENSION=1024
EMBEDDING_DEVICE=auto

RERANKER_BACKEND=cross-encoder
RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
RERANKER_DEVICE=auto

ASR_BACKEND=faster-whisper
ASR_MODEL_NAME=small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8

QDRANT_COLLECTION_NAME=document_chunks_e5_large_v1
```

Скачать модели заранее:

```bash
python -m scripts.download_models
```

`dimension` — размерность, то есть число компонентов embedding-вектора. При смене embedding-модели или размерности используй новое имя Qdrant collection, иначе в коллекции могут оказаться несовместимые векторы.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

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

Smoke test уже запущенного API:

```bash
python -m scripts.smoke_test
```

`smoke test` — короткая сквозная проверка основного сценария: healthcheck, создание документа, индексация и получение ответа.

## Полезные команды Docker

```bash
docker compose ps
docker compose logs -f postgres qdrant
docker compose restart postgres qdrant
docker compose down
```

Удалить только локальные данные инфраструктуры:

```bash
docker compose down -v
```

> Команда с `-v` необратимо удаляет Docker volumes.

## Переменные окружения

Основные группы настроек:

| Префикс | Назначение |
|---|---|
| `DATABASE_` | PostgreSQL и connection pool |
| `QDRANT_` | адрес, коллекция и batch upsert |
| `EMBEDDING_` | embedding backend и модель |
| `RERANKER_` | reranking backend и модель |
| `ASR_` | распознавание речи |
| `ANSWER_` | extractive или OpenAI-ответ |
| `CHUNK_` | размер и overlap текстовых чанков |
| `VIDEO_` | длительность и overlap видео-чанков |
| `MAX_` | ограничения размера загрузок |

Полный список значений находится в `.env.example` и `app/config.py`.
