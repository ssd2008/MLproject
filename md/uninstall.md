# Деинсталляция Асси

Команды нужно выполнять из папки репозитория, пока в ней находится `docker-compose.yml`.

## 1. Удали Docker-ресурсы Асси

```bash
docker compose down -v --rmi all --remove-orphans
```

Команда удаляет контейнеры, сети, образы и именованные volumes Compose-проекта. Вместе с volumes удаляются PostgreSQL, данные Qdrant, загруженные материалы и кэш моделей.

## 2. При необходимости очисти build cache

```bash
docker builder prune
```

> `docker builder prune` не ограничивается Асси: команда может удалить неиспользуемый кэш сборки других Docker-проектов. Перед удалением Docker покажет запрос подтверждения.

## 3. Удали репозиторий

macOS/Linux:

```bash
cd ..
rm -rf MLproject
```

Windows PowerShell:

```powershell
Set-Location ..
Remove-Item -Recurse -Force .\MLproject
```

После этого исходный код и Docker-ресурсы Асси будут удалены. Git, Docker Desktop и ресурсы других активных Docker-проектов останутся.

Проверить оставшиеся Docker-объекты:

```bash
docker compose ps --all
docker system df
```
