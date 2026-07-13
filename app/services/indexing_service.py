from __future__ import annotations

import logging
from uuid import UUID

from app.config import Settings
from app.exceptions import DocumentNotFoundError, IndexingError
from app.qdrant_schema import ChunkPayload, build_chunk_point_id, calculate_content_hash
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.vector_repository import VectorChunk, VectorRepository
from app.schemas import DocumentStatus
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractedDocument, PageSpan

logger = logging.getLogger(__name__)


class IndexingService:
    def __init__(
        self,
        *,
        settings: Settings,
        documents: DocumentRepository,
        jobs: JobRepository,
        vectors: VectorRepository,
        chunking: ChunkingService,
        embeddings: EmbeddingService,
    ) -> None:
        self._settings = settings
        self._documents = documents
        self._jobs = jobs
        self._vectors = vectors
        self._chunking = chunking
        self._embeddings = embeddings

    async def create_job(
        self,
        document_id: UUID,
        *,
        chunk_size: int | None,
        chunk_overlap: int | None,
    ):
        document = await self._documents.get_internal(document_id)
        if document is None:
            raise DocumentNotFoundError("Document not found", context={"document_id": str(document_id)})
        size = chunk_size or self._settings.chunk_size_tokens
        overlap = self._settings.chunk_overlap_tokens if chunk_overlap is None else chunk_overlap
        if overlap >= size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return await self._jobs.create(document_id, chunk_size=size, chunk_overlap=overlap)

    async def run_job(self, job_id: UUID, document_id: UUID) -> None:
        try:
            job = await self._jobs.get(job_id)
            if job is None:
                raise IndexingError("Indexing job disappeared before execution")
            await self._jobs.mark_running(job_id)
            await self._documents.update_status(document_id, DocumentStatus.PROCESSING)
            document = await self._documents.get_internal(document_id)
            if document is None:
                raise DocumentNotFoundError("Document not found")
            if not document.content_text:
                raise IndexingError("Document has no extracted text")

            spans = tuple(
                PageSpan(**item)
                for item in document.metadata.get("page_spans", [])
                if isinstance(item, dict)
                and {"page_number", "char_start", "char_end"} <= set(item)
            )
            chunks = self._chunking.split(
                ExtractedDocument(text=document.content_text, page_spans=spans),
                chunk_size=job.chunk_size,
                chunk_overlap=job.chunk_overlap,
            )
            if not chunks:
                raise IndexingError("Chunking produced no chunks")
            await self._jobs.update_progress(job_id, 25)

            vectors = await self._embeddings.embed_documents([chunk.text for chunk in chunks])
            await self._jobs.update_progress(job_id, 70)
            vector_chunks: list[VectorChunk] = []
            for chunk, vector in zip(chunks, vectors, strict=True):
                content_hash = calculate_content_hash(chunk.text)
                payload = ChunkPayload(
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                    document_title=document.title,
                    source_type=document.source_type,
                    source_url=document.source_url,
                    specialty=document.specialty,
                    lecture_date=document.lecture_date,
                    lecture_date_ordinal=(
                        document.lecture_date.toordinal() if document.lecture_date else None
                    ),
                    language=document.language,
                    content_hash=content_hash,
                )
                vector_chunks.append(
                    VectorChunk(
                        point_id=build_chunk_point_id(
                            document.id,
                            chunk.chunk_index,
                            content_hash,
                        ),
                        vector=vector,
                        payload=payload,
                    )
                )

            count = await self._vectors.replace_document_chunks(document.id, vector_chunks)
            await self._documents.finish_indexing(document.id, count)
            await self._jobs.complete(
                job_id,
                {
                    "document_id": str(document.id),
                    "chunks_count": count,
                    "embedding_backend": self._embeddings.backend_name,
                },
            )
        except Exception as exc:
            logger.exception("Indexing job %s failed", job_id)
            message = str(exc) or exc.__class__.__name__
            await self._jobs.fail(job_id, message)
            await self._documents.update_status(
                document_id,
                DocumentStatus.FAILED,
                error_message=message,
            )
