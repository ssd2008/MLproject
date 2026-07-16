import pytest
from pydantic import ValidationError

from app.schemas import AnswerRequest, DocumentCreate, SourceType


def test_text_document_requires_text() -> None:
    with pytest.raises(ValidationError):
        DocumentCreate(title="x", source_type=SourceType.TEXT)


def test_url_document_rejects_raw_text() -> None:
    with pytest.raises(ValidationError):
        DocumentCreate(
            title="x",
            source_type=SourceType.URL,
            source_url="https://example.com",
            raw_text="not allowed",
        )


def test_answer_context_cannot_exceed_top_k() -> None:
    with pytest.raises(ValidationError):
        AnswerRequest(query="test query", top_k=2, candidate_k=3, max_context_chunks=3)
