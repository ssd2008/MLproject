from fastapi import APIRouter, Depends

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas import AnswerOut, AnswerRequest

router = APIRouter(tags=["answers"])


@router.post("/answer", response_model=AnswerOut)
async def answer(
    request: AnswerRequest,
    container: AppContainer = Depends(get_container),
) -> AnswerOut:
    return await container.answer_service.answer(request)
