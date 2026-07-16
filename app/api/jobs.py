from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.container import AppContainer
from app.dependencies import get_container
from app.exceptions import JobNotFoundError
from app.schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: UUID,
    container: AppContainer = Depends(get_container),
) -> JobOut:
    job = await container.jobs.get(job_id)
    if job is None:
        raise JobNotFoundError("Indexing job not found", context={"job_id": str(job_id)})
    return job
