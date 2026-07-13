from fastapi import APIRouter, Depends, status

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas import FeedbackOut, FeedbackRequest

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    request: FeedbackRequest,
    container: AppContainer = Depends(get_container),
) -> FeedbackOut:
    feedback_id, created_at = await container.feedback.create(
        query=request.query,
        answer=request.answer,
        rating=request.rating,
        comment=request.comment,
        document_ids=request.document_ids,
        metadata=request.metadata,
    )
    return FeedbackOut(id=feedback_id, created_at=created_at)
