import pytest

from app.config import Settings
from app.exceptions import InvalidDocumentError
from app.services.extraction_service import ExtractionService, clean_text


def test_clean_text_normalizes_whitespace() -> None:
    assert clean_text(" a   b\r\n\r\n\r\n c ") == "a b\n\nc"


@pytest.mark.asyncio
async def test_private_url_is_rejected() -> None:
    service = ExtractionService(Settings())
    with pytest.raises(InvalidDocumentError):
        await service._validate_public_url("http://127.0.0.1/private")
