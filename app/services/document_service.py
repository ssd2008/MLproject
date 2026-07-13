from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from app.config import Settings
from app.exceptions import DocumentNotFoundError, InvalidDocumentError, UnsupportedMediaTypeError
from app.repositories.document_repository import DocumentRepository
from app.repositories.vector_repository import VectorRepository
from app.schemas import (
    DocumentCreate,
    DocumentOut,
    DocumentsListResponse,
    DocumentStatus,
    SourceType,
)
from app.services.extraction_service import ExtractionService


class DocumentService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: DocumentRepository,
        vector_repository: VectorRepository,
        extraction_service: ExtractionService,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._vectors = vector_repository
        self._extraction = extraction_service

    async def create(self, request: DocumentCreate) -> DocumentOut:
        if request.source_type == SourceType.TEXT:
            extracted = self._extraction.extract_text(request.raw_text or "")
            source_url = None
        elif request.source_type == SourceType.URL:
            source_url = str(request.source_url)
            extracted = await self._extraction.extract_url(source_url)
        else:
            raise InvalidDocumentError("PDF documents must use the upload endpoint")

        return await self._repository.create(
            title=request.title,
            source_type=request.source_type,
            source_url=source_url,
            content_text=extracted.text,
            specialty=request.specialty,
            lecture_date=request.lecture_date,
            language=request.language,
            metadata=request.metadata,
        )

    async def upload_pdf(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
        title: str,
        specialty: str | None,
        language: str,
        lecture_date,
        metadata_json: str | None,
    ) -> DocumentOut:
        if not filename.lower().endswith(".pdf"):
            raise UnsupportedMediaTypeError("Only .pdf files are accepted")
        if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
            raise UnsupportedMediaTypeError(f"Unsupported upload content type: {content_type}")
        if not data:
            raise InvalidDocumentError("Uploaded PDF is empty")
        if len(data) > self._settings.max_document_size_bytes:
            raise InvalidDocumentError(
                f"PDF exceeds the {self._settings.max_document_size_mb} MB limit"
            )
        try:
            metadata = json.loads(metadata_json) if metadata_json else {}
        except json.JSONDecodeError as exc:
            raise InvalidDocumentError("metadata must be a valid JSON object") from exc
        if not isinstance(metadata, dict):
            raise InvalidDocumentError("metadata must be a JSON object")

        extracted = await self._extraction.extract_pdf(data)
        upload_dir = self._settings.upload_dir
        await asyncio.to_thread(upload_dir.mkdir, parents=True, exist_ok=True)
        storage_path = upload_dir / f"{uuid4()}.pdf"
        await asyncio.to_thread(storage_path.write_bytes, data)
        checksum = hashlib.sha256(data).hexdigest()
        try:
            return await self._repository.create(
                title=title,
                source_type=SourceType.PDF,
                content_text=extracted.text,
                original_filename=Path(filename).name,
                storage_path=storage_path,
                mime_type="application/pdf",
                size_bytes=len(data),
                checksum_sha256=checksum,
                specialty=specialty,
                lecture_date=lecture_date,
                language=language,
                metadata={
                    **metadata,
                    "page_spans": [
                        {
                            "page_number": span.page_number,
                            "char_start": span.char_start,
                            "char_end": span.char_end,
                        }
                        for span in extracted.page_spans
                    ],
                },
            )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

    async def get(self, document_id: UUID) -> DocumentOut:
        document = await self._repository.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError("Document not found", context={"document_id": str(document_id)})
        return document

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        status: DocumentStatus | None,
        source_type: SourceType | None,
        specialty: str | None,
    ) -> DocumentsListResponse:
        items, total = await asyncio.gather(
            self._repository.list_documents(
                limit=limit,
                offset=offset,
                status=status,
                source_type=source_type,
                specialty=specialty,
            ),
            self._repository.count_documents(
                status=status,
                source_type=source_type,
                specialty=specialty,
            ),
        )
        return DocumentsListResponse(items=items, total=total, limit=limit, offset=offset)

    async def delete(self, document_id: UUID) -> None:
        document = await self._repository.get_internal(document_id)
        if document is None:
            raise DocumentNotFoundError("Document not found", context={"document_id": str(document_id)})
        await self._vectors.delete_document(document_id)
        deleted = await self._repository.delete(document_id)
        if deleted and deleted.storage_path:
            await asyncio.to_thread(deleted.storage_path.unlink, missing_ok=True)
