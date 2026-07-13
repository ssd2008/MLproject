from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg


class FeedbackRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        *,
        query: str,
        answer: str,
        rating: int,
        comment: str | None,
        document_ids: list[UUID],
        metadata: dict[str, Any],
    ) -> tuple[UUID, datetime]:
        record = await self._pool.fetchrow(
            """
            INSERT INTO feedback (
                id, query, answer, rating, comment, document_ids, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, created_at
            """,
            uuid4(),
            query,
            answer,
            rating,
            comment,
            document_ids,
            metadata,
        )
        if record is None:
            raise RuntimeError("PostgreSQL did not return the created feedback")
        return record["id"], record["created_at"]
