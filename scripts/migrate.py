from __future__ import annotations

import asyncio

import asyncpg

from app.config import BASE_DIR, settings


async def main() -> None:
    connection = await asyncpg.connect(settings.get_database_url())
    try:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for path in sorted((BASE_DIR / "sql").glob("*.sql")):
            applied = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name = $1)",
                path.name,
            )
            if applied:
                print(f"skip {path.name}")
                continue
            print(f"apply {path.name}")
            await connection.execute(path.read_text(encoding="utf-8"))
            await connection.execute(
                "INSERT INTO schema_migrations(name) VALUES ($1)",
                path.name,
            )
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
