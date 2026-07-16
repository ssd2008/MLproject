from app.services.chunking_service import ChunkingService
from app.services.extraction_service import ExtractedDocument, TimedTextSpan


def test_video_chunks_respect_timestamp_ranges() -> None:
    words = [f"слово{i}" for i in range(60)]
    text = " ".join(words)
    spans = []
    cursor = 0
    for index, word in enumerate(words):
        start = text.index(word, cursor)
        end = start + len(word)
        spans.append(
            TimedTextSpan(
                start_seconds=float(index),
                end_seconds=float(index + 1),
                char_start=start,
                char_end=end,
            )
        )
        cursor = end

    chunks = ChunkingService().split(
        ExtractedDocument(text=text, time_spans=tuple(spans)),
        chunk_size=400,
        chunk_overlap=80,
        max_time_seconds=20,
        time_overlap_seconds=2,
    )

    assert len(chunks) >= 3
    assert all(chunk.time_start_seconds is not None for chunk in chunks)
    assert all(chunk.time_end_seconds is not None for chunk in chunks)
    assert all(
        chunk.time_end_seconds - chunk.time_start_seconds <= 20
        for chunk in chunks
        if chunk.time_start_seconds is not None and chunk.time_end_seconds is not None
    )
    assert chunks[1].time_start_seconds < chunks[0].time_end_seconds
