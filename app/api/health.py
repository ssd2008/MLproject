from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Response, status

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas import ComponentHealth, HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def healthcheck(
    response: Response,
    container: AppContainer = Depends(get_container),
) -> HealthOut:
    async def check_postgres() -> ComponentHealth:
        try:
            await container.documents.ping()
            return ComponentHealth(status="ok")
        except Exception as exc:
            return ComponentHealth(status="error", detail=str(exc))

    async def check_qdrant() -> ComponentHealth:
        try:
            await container.vectors.ping()
            return ComponentHealth(status="ok")
        except Exception as exc:
            return ComponentHealth(status="error", detail=str(exc))

    postgres, qdrant = await asyncio.gather(check_postgres(), check_qdrant())
    components = {
        "postgres": postgres,
        "qdrant": qdrant,
        "embedding": ComponentHealth(
            status="ok",
            detail=container.embeddings.backend_name,
        ),
        "reranker": ComponentHealth(
            status="ok",
            detail=container.reranker.backend_name,
        ),
        "answer": ComponentHealth(
            status="ok",
            detail=container.answer_service.backend_name,
        ),
    }
    overall = "ok" if all(item.status != "error" for item in components.values()) else "degraded"
    if overall == "degraded":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(
        status=overall,
        service=container.settings.app_name,
        version=container.settings.app_version,
        components=components,
    )
