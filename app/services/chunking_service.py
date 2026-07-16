from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.extraction_service import (
    ExtractedDocument,
    PageSpan,
    TimedTextSpan,
    clean_text,
)

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
    time_start_seconds: float | None
    time_end_seconds: float | None
    section_title: str | None


class ChunkingService:
    """Deterministic chunking with character, page and optional media-time offsets."""

    def split(
        self,
        document: ExtractedDocument,
        *,
        chunk_size: int,
        chunk_overlap: int,
        max_time_seconds: float | None = None,
        time_overlap_seconds: float = 0.0,
    ) -> list[TextChunk]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
        if max_time_seconds is not None:
            if max_time_seconds <= 0:
                raise ValueError("max_time_seconds must be positive")
            if time_overlap_seconds < 0 or time_overlap_seconds >= max_time_seconds:
                raise ValueError(
                    "time_overlap_seconds must be non-negative and smaller than max_time_seconds"
                )

        text = clean_text(document.text)
        if document.time_spans and max_time_seconds is not None:
            return self._split_timed(
                text,
                document.time_spans,
                chunk_size=chunk_size,
                max_time_seconds=max_time_seconds,
                time_overlap_seconds=time_overlap_seconds,
            )

        matches = list(_TOKEN_PATTERN.finditer(text))
        if not matches:
            return []

        headings = [
            (match.start(), match.group(0).lstrip("# ").strip())
            for match in _HEADING_PATTERN.finditer(text)
        ]
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
            time_start, time_end = self._time_range(
                char_start,
                char_end,
                document.time_spans,
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
                    time_start_seconds=time_start,
                    time_end_seconds=time_end,
                    section_title=self._section_title(char_start, headings),
                )
            )
            if end_token == len(matches):
                break
        return result

    def _split_timed(
        self,
        text: str,
        spans: tuple[TimedTextSpan, ...],
        *,
        chunk_size: int,
        max_time_seconds: float,
        time_overlap_seconds: float,
    ) -> list[TextChunk]:
        ordered = sorted(spans, key=lambda span: (span.start_seconds, span.char_start))
        result: list[TextChunk] = []
        start_index = 0

        while start_index < len(ordered):
            first = ordered[start_index]
            end_index = start_index
            while end_index + 1 < len(ordered):
                candidate = ordered[end_index + 1]
                duration = candidate.end_seconds - first.start_seconds
                token_count = end_index + 2 - start_index
                if duration > max_time_seconds or token_count > chunk_size:
                    break
                end_index += 1

            last = ordered[end_index]
            char_start = first.char_start
            char_end = last.char_end
            chunk_text = text[char_start:char_end].strip()
            if chunk_text:
                result.append(
                    TextChunk(
                        chunk_index=len(result),
                        text=chunk_text,
                        token_count=end_index - start_index + 1,
                        char_start=char_start,
                        char_end=char_end,
                        page_start=None,
                        page_end=None,
                        time_start_seconds=round(first.start_seconds, 3),
                        time_end_seconds=round(last.end_seconds, 3),
                        section_title=None,
                    )
                )

            if end_index == len(ordered) - 1:
                break

            overlap_target = last.end_seconds - time_overlap_seconds
            next_index = start_index + 1
            while (
                next_index <= end_index
                and ordered[next_index].start_seconds < overlap_target
            ):
                next_index += 1
            start_index = max(start_index + 1, next_index)

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

    @staticmethod
    def _time_range(
        char_start: int,
        char_end: int,
        time_spans: tuple[TimedTextSpan, ...],
    ) -> tuple[float | None, float | None]:
        relevant = [
            span
            for span in time_spans
            if span.char_start < char_end and span.char_end > char_start
        ]
        if not relevant:
            return None, None
        return min(span.start_seconds for span in relevant), max(
            span.end_seconds for span in relevant
        )
