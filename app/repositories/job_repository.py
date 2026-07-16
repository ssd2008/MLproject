from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.schemas import JobOut, JobStatus

_JOB_COLUMNS = """
    id, document_id, status, progress, chunk_size, chunk_overlap,
    result, error_message, created_at, started_at, finished_at, updated_at
"""


class JobRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def _to_job(record: asyncpg.Record) -> JobOut:
        return JobOut.model_validate(dict(record))

    async def create(self, document_id: UUID, *, chunk_size: int, chunk_overlap: int) -> JobOut:
        record = await self._pool.fetchrow(
            f"""
            INSERT INTO index_jobs (id, document_id, status, chunk_size, chunk_overlap)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING {_JOB_COLUMNS}
            """,
            uuid4(),
            document_id,
            JobStatus.PENDING.value,
            chunk_size,
            chunk_overlap,
        )
        if record is None:
            raise RuntimeError("PostgreSQL did not return the created job")
        return self._to_job(record)

    async def get(self, job_id: UUID) -> JobOut | None:
        record = await self._pool.fetchrow(
            f"SELECT {_JOB_COLUMNS} FROM index_jobs WHERE id = $1",
            job_id,
        )
        return self._to_job(record) if record else None

    async def mark_running(self, job_id: UUID, *, progress: int = 1) -> None:
        await self._pool.execute(
            """
            UPDATE index_jobs
            SET status = $2, progress = $3, started_at = COALESCE(started_at, NOW())
            WHERE id = $1
            """,
            job_id,
            JobStatus.RUNNING.value,
            progress,
        )

    async def update_progress(self, job_id: UUID, progress: int) -> None:
        await self._pool.execute(
            "UPDATE index_jobs SET progress = $2 WHERE id = $1",
            job_id,
            max(0, min(progress, 99)),
        )

    async def complete(self, job_id: UUID, result: dict[str, Any]) -> None:
        await self._pool.execute(
            """
            UPDATE index_jobs
            SET status = $2, progress = 100, result = $3,
                error_message = NULL, finished_at = NOW()
            WHERE id = $1
            """,
            job_id,
            JobStatus.COMPLETED.value,
            result,
        )

    async def fail(self, job_id: UUID, error_message: str) -> None:
        await self._pool.execute(
            """
            UPDATE index_jobs
            SET status = $2, error_message = $3, finished_at = NOW()
            WHERE id = $1
            """,
            job_id,
            JobStatus.FAILED.value,
            error_message[:5000],
        )
