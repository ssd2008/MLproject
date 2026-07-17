# Типовые проблемы

Для просмотра состояние контейнеров и логов:

```bash
docker compose ps
docker compose logs --tail=200
```

В таблице `docker compose ps` сервисы `postgres`, `qdrant`, `api` и `frontend` должны быть запущены. Одноразовые сервисы `migrate` и `model-init` после успешного завершения могут иметь состояние `Exited (0)` — это нормально.

## `docker: command not found`

Docker Desktop не установлен либо терминал был открыт до установки.

1. Установи Docker Desktop:
   - [macOS](install_macos.md);
   - [Windows](install_windows.md).
2. Запусти Docker Desktop.
3. Полностью перезапусти терминал.
4. Проверь:

```bash
docker --version
docker compose version
```

## `Cannot connect to the Docker daemon`

Docker CLI установлен, но Docker Engine не запущен.

- открой Docker Desktop;
- дождись запуска Engine;
- повтори команду.

Проверка:

```bash
docker info
```

## Первый запуск долго стоит на `model-init`

`model-init` скачивает embedding-модель, reranker и Whisper-модель. Это может занимать значительное время в зависимости от сети, диска и CPU.

Логи:

```bash
docker compose logs -f model-init
```

Проверь:

- доступ в интернет;
- свободное место на диске;
- что Docker Desktop не остановлен;
- отсутствие корпоративного proxy/firewall, блокирующего Hugging Face.

Повторный запуск использует постоянный cache volume и обычно быстрее.

## Сборка зависла на `exporting layers`

Docker сохраняет большой image backend с ML-зависимостями. На медленном диске эта стадия может быть долгой.

Проверка места:

```bash
docker system df
```

Очистка неиспользуемого build cache:

```bash
docker builder prune
```

Более агрессивная очистка:

```bash
docker system prune
```

> Перед очисткой прочитай список удаляемых объектов. Не добавляй `--volumes`, если не готов удалить локальные данные других Docker-проектов.

## Порт уже занят

Проект использует порты:

- `3000` — frontend;
- `8000` — API;
- `5432` — PostgreSQL;
- `6333` и `6334` — Qdrant.

### macOS

```bash
lsof -i :3000
lsof -i :8000
lsof -i :5432
lsof -i :6333
```

### Windows PowerShell

```powershell
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 5432 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 6333 -ErrorAction SilentlyContinue
```

Останови конфликтующий процесс или измени левую часть port mapping в `docker-compose.yml`, например:

```yaml
ports:
  - "8001:8000"
```

После этого API будет доступен на порту `8001`.

## PostgreSQL сообщает `role "med_user" does not exist`

Обычно локальный API подключается не к PostgreSQL из Docker либо используется старый volume с другой конфигурацией.

Проверь `.env` для локального запуска:

```dotenv
DATABASE_URL=postgresql://med_user:med_pass@localhost:5432/med_assistant
```

Проверь контейнер:

```bash
docker compose ps postgres
docker compose logs postgres
```

Полный сброс только для тестовых локальных данных:

```bash
docker compose down -v
docker compose up --build
```

> Эта команда удалит все документы и индексы проекта.

## API возвращает `503` на `/health`

Посмотри компоненты ответа:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Затем проверь логи:

```bash
docker compose logs --tail=200 postgres qdrant api
```

`503` означает, что PostgreSQL или Qdrant недоступны. Состояние `disabled` для ASR допустимо только в лёгком режиме.

## Frontend не открывается, но API работает

Проверь:

```bash
docker compose ps frontend
docker compose logs --tail=200 frontend
```

Затем открой напрямую:

```text
http://127.0.0.1:3000
```

Не используй `https://`: локальный Docker Compose поднимает HTTP.

## PDF загружен, но индексация завершается ошибкой

Проект извлекает текстовый слой PDF. Скан, состоящий только из изображений, без OCR не поддерживается.

Проверь PDF: попробуй выделить и скопировать текст в обычном просмотрщике. Если текст не выделяется, сначала распознай документ внешним OCR-инструментом.

## Видео не загружается

Проверь:

- размер файла не превышает `MAX_VIDEO_SIZE_MB`, по умолчанию 500 МБ;
- формат поддерживается;
- сервис `model-init` завершился успешно;
- ASR backend не отключён;
- в Docker достаточно места.

Логи:

```bash
docker compose logs --tail=300 api
```

## После смены embedding-модели Qdrant сообщает несовпадение размерности

Qdrant collection создаётся под определённую размерность векторов. При смене модели или `EMBEDDING_DIMENSION` задай новое имя:

```dotenv
QDRANT_COLLECTION_NAME=document_chunks_new_model_v1
```

`dimension` — размерность embedding-вектора. Векторы разных размерностей нельзя хранить в одной коллекции.

## `ModuleNotFoundError: No module named 'app'`

Запускай команды из корня репозитория и используй модульный запуск:

```bash
python -m scripts.migrate
python -m scripts.smoke_test
```

Не запускай:

```bash
python scripts/migrate.py
```

При модульном запуске корень проекта добавляется в Python import path.

## Windows: ошибка WSL или виртуализации

В PowerShell от администратора:

```powershell
wsl --update
wsl --shutdown
```

Перезагрузи компьютер и Docker Desktop. Если ошибка сохраняется, проверь аппаратную виртуализацию в BIOS/UEFI и настройки WSL 2 в Docker Desktop.

## Получить полный диагностический вывод

```bash
docker compose ps
docker compose images
docker compose logs --tail=300
docker system df
```

Не публикуй `.env`, API-ключи, пароли и персональные данные из загруженных материалов.
