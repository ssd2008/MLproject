from __future__ import annotations

import json

import asyncpg

from app.config import Settings


async def _configure_connection(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
        format="text",
    )


async def create_database_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=settings.get_database_url(),
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        command_timeout=settings.database_command_timeout_seconds,
        init=_configure_connection,
    )
