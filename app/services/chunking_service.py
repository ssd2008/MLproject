from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.extraction_service import ExtractedDocument, PageSpan, clean_text

_TOKEN_PATTERN = re.compile(r"\S+")
_HEADING_PATTERN = re.compile(r"(?m)^(?:#{1,6}\s+.+|[A-ZА-ЯЁ][A-ZА-ЯЁ0-9 .,:;()\-/]{4,})$")


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_index: int
    text: str
    token_count: int
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    section_title: str | None


class ChunkingService:
    """Deterministic whitespace-token chunking with exact character offsets."""

    def split(
        self,
        document: ExtractedDocument,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[TextChunk]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

        text = clean_text(document.text)
        matches = list(_TOKEN_PATTERN.finditer(text))
        if not matches:
            return []

        headings = [(match.start(), match.group(0).lstrip("# ").strip()) for match in _HEADING_PATTERN.finditer(text)]
        step = chunk_size - chunk_overlap
        result: list[TextChunk] = []

        for start_token in range(0, len(matches), step):
            end_token = min(start_token + chunk_size, len(matches))
            char_start = matches[start_token].start()
            char_end = matches[end_token - 1].end()
            chunk_text = text[char_start:char_end].strip()
            if not chunk_text:
                continue
            page_start, page_end = self._page_range(
                char_start,
                char_end,
                document.page_spans,
            )
            result.append(
                TextChunk(
                    chunk_index=len(result),
                    text=chunk_text,
                    token_count=end_token - start_token,
                    char_start=char_start,
                    char_end=char_end,
                    page_start=page_start,
                    page_end=page_end,
                    section_title=self._section_title(char_start, headings),
                )
            )
            if end_token == len(matches):
                break
        return result

    @staticmethod
    def _section_title(offset: int, headings: list[tuple[int, str]]) -> str | None:
        title: str | None = None
        for position, candidate in headings:
            if position > offset:
                break
            title = candidate[:500]
        return title

    @staticmethod
    def _page_range(
        char_start: int,
        char_end: int,
        page_spans: tuple[PageSpan, ...],
    ) -> tuple[int | None, int | None]:
        pages = [
            span.page_number
            for span in page_spans
            if span.char_start < char_end and span.char_end > char_start
        ]
        return (min(pages), max(pages)) if pages else (None, None)
