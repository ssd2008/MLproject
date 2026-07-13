from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from qdrant_client import AsyncQdrantClient, models

from app.qdrant_schema import (
    DEFAULT_COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    PAYLOAD_INDEXES,
    ChunkPayload,
    SourceType,
)


class VectorRepositoryError(RuntimeError):
    """Base error raised by the Qdrant repository."""


class VectorCollectionSchemaError(VectorRepositoryError):
    """The existing collection is incompatible with the expected schema."""


class VectorPayloadError(VectorRepositoryError):
    """A Qdrant point contains an invalid or unexpected payload."""


@dataclass(frozen=True, slots=True)
class VectorChunk:
    """
    Chunk prepared for insertion into Qdrant.

    point_id:
        Deterministic Qdrant point UUID.

    vector:
        Dense embedding with exactly `vector_size` elements.

    payload:
        Validated metadata and source text.
    """

    point_id: UUID
    vector: Sequence[float]
    payload: ChunkPayload


@dataclass(frozen=True, slots=True)
class StoredVectorChunk:
    """Chunk read from Qdrant without a similarity score."""

    point_id: UUID
    payload: ChunkPayload
    vector: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """Chunk returned by vector similarity search."""

    point_id: UUID
    score: float
    payload: ChunkPayload


class VectorRepository:
    """
    Asynchronous data-access layer for chunk vectors stored in Qdrant.

    The repository does not calculate embeddings. It only validates,
    stores, searches and deletes already prepared vectors.
    """

    def __init__(
        self,
        client: AsyncQdrantClient,
        *,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_size: int,
        upsert_batch_size: int = 64,
        scroll_page_size: int = 256,
    ) -> None:
        if not collection_name.strip():
            raise ValueError("collection_name must not be empty")
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        if upsert_batch_size <= 0:
            raise ValueError("upsert_batch_size must be positive")
        if scroll_page_size <= 0:
            raise ValueError("scroll_page_size must be positive")

        self._client = client
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._upsert_batch_size = upsert_batch_size
        self._scroll_page_size = scroll_page_size

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @property
    def vector_size(self) -> int:
        return self._vector_size

    async def ping(self) -> None:
        """Check that the Qdrant service is reachable."""

        await self._client.get_collections()

    async def ensure_collection(self) -> None:
        """
        Create the collection and payload indexes or validate them.

        ensure means "make sure": after this method completes, the
        collection is expected to exist with the required schema.
        """

        exists = await self._client.collection_exists(
            self._collection_name
        )

        if not exists:
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(
                        size=self._vector_size,
                        distance=models.Distance.COSINE,
                    )
                },
                on_disk_payload=True,
            )

        collection_info = await self._client.get_collection(
            self._collection_name
        )
        self._validate_collection_schema(collection_info)
        await self._ensure_payload_indexes(collection_info)

    async def upsert_chunks(
        self,
        chunks: Sequence[VectorChunk],
    ) -> int:
        """
        Insert new points or replace existing points with equal IDs.

        upsert = update + insert:
        update the point if its ID exists, otherwise insert it.
        """

        if not chunks:
            return 0

        points = [self._to_point_struct(chunk) for chunk in chunks]

        for start in range(
            0,
            len(points),
            self._upsert_batch_size,
        ):
            batch = points[
                start : start + self._upsert_batch_size
            ]
            await self._client.upsert(
                collection_name=self._collection_name,
                points=batch,
                wait=True,
            )

        return len(points)

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 10,
        score_threshold: float | None = None,
        document_ids: Sequence[UUID] | None = None,
        specialty: str | None = None,
        source_type: SourceType | None = None,
        language: str | None = None,
    ) -> list[VectorSearchResult]:
        """
        Return chunks nearest to the query vector.

        score_threshold:
            threshold means "порог". Points with a lower cosine score
            are excluded by Qdrant.

        document_ids, specialty, source_type and language are combined
        with logical AND.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")

        if (
            score_threshold is not None
            and not math.isfinite(score_threshold)
        ):
            raise ValueError(
                "score_threshold must be a finite number"
            )

        vector = self._validate_vector(query_vector)
        query_filter = self._build_search_filter(
            document_ids=document_ids,
            specialty=specialty,
            source_type=source_type,
            language=language,
        )

        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            using=DENSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            score_threshold=score_threshold,
        )

        return [
            self._search_result_from_point(point)
            for point in response.points
        ]

    async def get_chunks_by_document(
        self,
        document_id: UUID,
        *,
        with_vectors: bool = False,
    ) -> list[StoredVectorChunk]:
        """
        Return every indexed chunk of a document.

        Qdrant scroll order is not treated as chunk order, so the
        result is explicitly sorted by payload.chunk_index.
        """

        records = await self._scroll_all(
            scroll_filter=self._document_filter(document_id),
            with_vectors=with_vectors,
        )

        chunks = [
            self._stored_chunk_from_record(record)
            for record in records
        ]
        chunks.sort(
            key=lambda chunk: chunk.payload.chunk_index
        )
        return chunks

    async def get_neighbor_chunks(
        self,
        document_id: UUID,
        chunk_index: int,
        *,
        window: int = 1,
        with_vectors: bool = False,
    ) -> list[StoredVectorChunk]:
        """
        Return the target chunk and nearby chunks from one document.

        window:
            number of chunks requested on each side. For example,
            chunk_index=5 and window=2 requests indexes 3..7.
        """

        if chunk_index < 0:
            raise ValueError(
                "chunk_index must be non-negative"
            )
        if window < 0:
            raise ValueError("window must be non-negative")

        start_index = max(0, chunk_index - window)
        end_index = chunk_index + window

        scroll_filter = models.Filter(
            must=[
                self._match_value_condition(
                    "document_id",
                    str(document_id),
                ),
                models.FieldCondition(
                    key="chunk_index",
                    range=models.Range(
                        gte=start_index,
                        lte=end_index,
                    ),
                ),
            ]
        )

        records = await self._scroll_all(
            scroll_filter=scroll_filter,
            with_vectors=with_vectors,
        )

        chunks = [
            self._stored_chunk_from_record(record)
            for record in records
        ]
        chunks.sort(
            key=lambda chunk: chunk.payload.chunk_index
        )
        return chunks

    async def count_by_document_id(
        self,
        document_id: UUID,
    ) -> int:
        """Return the exact number of chunks for a document."""

        result = await self._client.count(
            collection_name=self._collection_name,
            count_filter=self._document_filter(document_id),
            exact=True,
        )
        return result.count

    async def delete_by_document_id(
        self,
        document_id: UUID,
    ) -> int:
        """
        Delete every chunk of a document.

        Returns the number of matching points counted immediately
        before deletion. Qdrant's delete response itself does not
        contain the number of deleted points.
        """

        count = await self.count_by_document_id(document_id)
        if count == 0:
            return 0

        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=self._document_filter(document_id)
            ),
            wait=True,
        )
        return count

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> VectorRepository:
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc: Any,
        traceback: Any,
    ) -> None:
        await self.close()

    async def _ensure_payload_indexes(
        self,
        collection_info: models.CollectionInfo,
    ) -> None:
        existing_indexes = collection_info.payload_schema

        for field_name, expected_type in PAYLOAD_INDEXES.items():
            existing_index = existing_indexes.get(field_name)

            if existing_index is None:
                await self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field_name,
                    field_schema=expected_type,
                    wait=True,
                )
                continue

            actual_type = existing_index.data_type
            if actual_type != expected_type:
                raise VectorCollectionSchemaError(
                    f"Payload index {field_name!r} has type "
                    f"{actual_type!r}; expected {expected_type!r}."
                )

    def _validate_collection_schema(
        self,
        collection_info: models.CollectionInfo,
    ) -> None:
        vectors_config = (
            collection_info.config.params.vectors
        )

        if not isinstance(vectors_config, dict):
            raise VectorCollectionSchemaError(
                f"Collection {self._collection_name!r} uses "
                "an unnamed vector; expected named vector "
                f"{DENSE_VECTOR_NAME!r}."
            )

        dense_config = vectors_config.get(
            DENSE_VECTOR_NAME
        )
        if dense_config is None:
            raise VectorCollectionSchemaError(
                f"Collection {self._collection_name!r} "
                f"does not contain vector "
                f"{DENSE_VECTOR_NAME!r}."
            )

        if dense_config.size != self._vector_size:
            raise VectorCollectionSchemaError(
                "Vector dimension mismatch: "
                f"collection={dense_config.size}, "
                f"repository={self._vector_size}."
            )

        if (
            dense_config.distance
            != models.Distance.COSINE
        ):
            raise VectorCollectionSchemaError(
                "Distance mismatch: "
                f"collection={dense_config.distance!r}, "
                f"expected={models.Distance.COSINE!r}."
            )

    def _to_point_struct(
        self,
        chunk: VectorChunk,
    ) -> models.PointStruct:
        vector = self._validate_vector(chunk.vector)

        return models.PointStruct(
            id=str(chunk.point_id),
            vector={
                DENSE_VECTOR_NAME: vector,
            },
            payload=chunk.payload.to_qdrant_payload(),
        )

    def _validate_vector(
        self,
        vector: Sequence[float],
    ) -> list[float]:
        values = [float(value) for value in vector]

        if len(values) != self._vector_size:
            raise ValueError(
                "Vector dimension must be "
                f"{self._vector_size}, got {len(values)}"
            )

        if not all(
            math.isfinite(value)
            for value in values
        ):
            raise ValueError(
                "Vector contains NaN or infinity"
            )

        return values

    @classmethod
    def _build_search_filter(
        cls,
        *,
        document_ids: Sequence[UUID] | None,
        specialty: str | None,
        source_type: SourceType | None,
        language: str | None,
    ) -> models.Filter | None:
        conditions: list[models.Condition] = []

        if document_ids is not None:
            ids = [
                str(document_id)
                for document_id in document_ids
            ]

            if not ids:
                raise ValueError(
                    "document_ids must not be empty "
                    "when provided"
                )

            if len(ids) == 1:
                conditions.append(
                    cls._match_value_condition(
                        "document_id",
                        ids[0],
                    )
                )
            else:
                conditions.append(
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchAny(any=ids),
                    )
                )

        for field_name, value in (
            ("specialty", specialty),
            ("source_type", source_type),
            ("language", language),
        ):
            if value is not None:
                conditions.append(
                    cls._match_value_condition(
                        field_name,
                        value,
                    )
                )

        if not conditions:
            return None

        return models.Filter(must=conditions)

    @staticmethod
    def _match_value_condition(
        key: str,
        value: str,
    ) -> models.FieldCondition:
        return models.FieldCondition(
            key=key,
            match=models.MatchValue(value=value),
        )

    @classmethod
    def _document_filter(
        cls,
        document_id: UUID,
    ) -> models.Filter:
        return models.Filter(
            must=[
                cls._match_value_condition(
                    "document_id",
                    str(document_id),
                )
            ]
        )

    async def _scroll_all(
        self,
        *,
        scroll_filter: models.Filter,
        with_vectors: bool,
    ) -> list[models.Record]:
        """
        Read every page returned by Qdrant scroll.

        scroll means sequentially reading matching points page by
        page without similarity ranking.
        """

        records: list[models.Record] = []
        offset: models.ExtendedPointId | None = None

        while True:
            page, next_offset = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=scroll_filter,
                limit=self._scroll_page_size,
                offset=offset,
                with_payload=True,
                with_vectors=(
                    [DENSE_VECTOR_NAME]
                    if with_vectors
                    else False
                ),
            )

            records.extend(page)

            if next_offset is None:
                break

            offset = next_offset

        return records

    def _search_result_from_point(
        self,
        point: models.ScoredPoint,
    ) -> VectorSearchResult:
        return VectorSearchResult(
            point_id=self._parse_point_id(point.id),
            score=float(point.score),
            payload=self._parse_payload(point.payload),
        )

    def _stored_chunk_from_record(
        self,
        record: models.Record,
    ) -> StoredVectorChunk:
        vector: tuple[float, ...] | None = None

        if record.vector is not None:
            if not isinstance(record.vector, dict):
                raise VectorPayloadError(
                    f"Point {record.id!r} returned "
                    "an unnamed vector"
                )

            raw_vector = record.vector.get(
                DENSE_VECTOR_NAME
            )

            if (
                raw_vector is None
                or not isinstance(raw_vector, list)
            ):
                raise VectorPayloadError(
                    f"Point {record.id!r} has no "
                    f"{DENSE_VECTOR_NAME!r} vector"
                )

            vector = tuple(
                float(value)
                for value in raw_vector
            )

        return StoredVectorChunk(
            point_id=self._parse_point_id(record.id),
            payload=self._parse_payload(record.payload),
            vector=vector,
        )

    @staticmethod
    def _parse_point_id(
        point_id: models.ExtendedPointId,
    ) -> UUID:
        try:
            return UUID(str(point_id))
        except (TypeError, ValueError) as exc:
            raise VectorPayloadError(
                "Expected UUID point ID, received "
                f"{point_id!r}"
            ) from exc

    @staticmethod
    def _parse_payload(
        payload: dict[str, Any] | None,
    ) -> ChunkPayload:
        if payload is None:
            raise VectorPayloadError(
                "Qdrant point has no payload"
            )

        try:
            return ChunkPayload.model_validate(payload)
        except ValidationError as exc:
            raise VectorPayloadError(
                "Qdrant point payload is invalid"
            ) from exc
