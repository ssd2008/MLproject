# Деинсталяция

Удаляем docker-контейнеры и кэш:

```Bash
docker compose down -v --rmi all --remove-orphans
docker builder prune
```

Затем удалить сам репозиторий.

macOS/Linux:

```Bash
cd ..
rm -rf MLproject
```

Windows PowerShell:

```Bash
cd ..
Remove-Item -Recurse -Force .\MLproject
```

После этого от проекта почти ничего не останется.
