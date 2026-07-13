from fastapi import APIRouter, Depends

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas import QueryRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    request: QueryRequest,
    container: AppContainer = Depends(get_container),
) -> SearchResponse:
    return await container.search_service.search(request)
