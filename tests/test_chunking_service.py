from app.services.chunking_service import ChunkingService
from app.services.extraction_service import ExtractedDocument, PageSpan


def test_chunking_has_overlap_and_offsets() -> None:
    text = "one two three four five six seven eight nine ten"
    chunks = ChunkingService().split(
        ExtractedDocument(text=text),
        chunk_size=4,
        chunk_overlap=1,
    )
    assert [chunk.text for chunk in chunks] == [
        "one two three four",
        "four five six seven",
        "seven eight nine ten",
    ]
    assert text[chunks[1].char_start : chunks[1].char_end] == chunks[1].text
    assert chunks[0].token_count == 4


def test_chunking_maps_pdf_pages() -> None:
    text = "page one text\n\npage two text"
    chunks = ChunkingService().split(
        ExtractedDocument(
            text=text,
            page_spans=(
                PageSpan(page_number=1, char_start=0, char_end=13),
                PageSpan(page_number=2, char_start=15, char_end=len(text)),
            ),
        ),
        chunk_size=20,
        chunk_overlap=0,
    )
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2
