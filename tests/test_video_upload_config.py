from io import BytesIO
from pathlib import Path

import pytest

from app.config import Settings
from app.exceptions import InvalidDocumentError
from app.services.document_service import (
    DocumentService,
    _ALLOWED_VIDEO_MIME_TYPES,
    _VIDEO_TYPES,
)


def test_default_video_limit_is_two_gibibytes() -> None:
    assert Settings.model_fields["max_video_size_mb"].default == 2048
    assert Settings(max_video_size_mb=2048).max_video_size_bytes == 2 * 1024**3


def test_mkv_is_supported_case_insensitively() -> None:
    assert Path("lecture.MKV").suffix.lower() in _VIDEO_TYPES
    assert _VIDEO_TYPES[".mkv"] == "video/x-matroska"
    assert "video/matroska" in _ALLOWED_VIDEO_MIME_TYPES


def test_video_stream_is_written_incrementally(tmp_path: Path) -> None:
    target = tmp_path / "lecture.mkv"
    size_bytes, checksum = DocumentService._store_video_stream(
        BytesIO(b"matroska-data"),
        target,
        1024,
    )

    assert size_bytes == len(b"matroska-data")
    assert len(checksum) == 64
    assert target.read_bytes() == b"matroska-data"


def test_oversized_video_stream_is_removed(tmp_path: Path) -> None:
    target = tmp_path / "oversized.mkv"

    with pytest.raises(InvalidDocumentError, match="exceeds"):
        DocumentService._store_video_stream(BytesIO(b"1234"), target, 3)

    assert not target.exists()
