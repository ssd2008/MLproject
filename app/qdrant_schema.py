from __future__ import annotations

from datetime import date
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from qdrant_client import QdrantClient, models


DEFAULT_COLLECTION_NAME = "document_chunks_v1"
DENSE_VECTOR_NAME = "dense"
PAYLOAD_SCHEMA_VERSION = 1


SourceType = Literal["pdf", "url", "text"]


class ChunkPayload(BaseModel):
    """
    Строгая схема payload одной точки Qdrant.

    Point ID хранится отдельно в Qdrant и является chunk_id.
    Поэтому chunk_id здесь намеренно не дублируется.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    schema_version: Literal[1] = PAYLOAD_SCHEMA_VERSION

    document_id: UUID
    chunk_index: int = Field(ge=0)

    text: str = Field(min_length=1)
    token_count: int = Field(gt=0)

    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)

    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_title: str | None = Field(default=None, max_length=500)

    document_title: str = Field(min_length=1, max_length=1000)
    source_type: SourceType
    source_url: str | None = Field(default=None, max_length=4000)

    specialty: str | None = Field(default=None, max_length=100)
    lecture_date: date | None = None
    language: str = Field(default="ru", min_length=2, max_length=16)

    content_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_ranges(self) -> "ChunkPayload":
        if self.char_end <= self.char_start:
            raise ValueError(
                "char_end must be greater than char_start"
            )

        exactly_one_page_boundary_is_missing = (
            (self.page_start is None) != (self.page_end is None)
        )
        if exactly_one_page_boundary_is_missing:
            raise ValueError(
                "page_start and page_end must either both be set "
                "or both be None"
            )

        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError(
                "page_end must be greater than or equal to page_start"
            )

        if self.source_type != "url" and self.source_url is not None:
            raise ValueError(
                "source_url may only be set for source_type='url'"
            )

        return self

    def to_qdrant_payload(self) -> dict[str, object]:
        """
        mode='json' преобразует UUID и date в JSON-совместимые строки.
        """

        return self.model_dump(
            mode="json",
            exclude_none=True,
        )


PAYLOAD_INDEXES: dict[str, models.PayloadSchemaType] = {
    "document_id": models.PayloadSchemaType.UUID,
    "chunk_index": models.PayloadSchemaType.INTEGER,
    "source_type": models.PayloadSchemaType.KEYWORD,
    "specialty": models.PayloadSchemaType.KEYWORD,
    "lecture_date": models.PayloadSchemaType.DATETIME,
    "language": models.PayloadSchemaType.KEYWORD,
}


def calculate_content_hash(text: str) -> str:
    """
    Возвращает SHA-256 хеш нормализованного текста.

    hexdigest:
        hexadecimal digest — шестнадцатеричное представление хеша.
    """

    normalized_text = text.strip()
    return sha256(normalized_text.encode("utf-8")).hexdigest()


def build_chunk_point_id(
    document_id: UUID,
    chunk_index: int,
    content_hash: str,
) -> UUID:
    """
    Создаёт детерминированный UUID точки.

    uuid5:
        UUID version 5 — UUID, вычисляемый из namespace и строки
        с помощью SHA-1.

    Здесь document_id используется как namespace.
    Одинаковый chunk всегда получает одинаковый point ID.
    """

    if chunk_index < 0:
        raise ValueError("chunk_index must be non-negative")

    if len(content_hash) != 64:
        raise ValueError("content_hash must be a SHA-256 hex digest")

    return uuid5(
        document_id,
        f"{chunk_index}:{content_hash}",
    )


def ensure_qdrant_collection(
    client: QdrantClient,
    *,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    vector_size: int,
) -> None:
    """
    Создаёт коллекцию и payload-индексы либо проверяет
    совместимость существующей коллекции.
    """

    if vector_size <= 0:
        raise ValueError("vector_size must be positive")

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            },
            # Основной объём payload занимает text.
            # Его нет необходимости постоянно держать в RAM.
            on_disk_payload=True,
        )

    _validate_collection(
        client=client,
        collection_name=collection_name,
        expected_vector_size=vector_size,
    )

    collection_info = client.get_collection(collection_name)
    existing_indexes = set(collection_info.payload_schema.keys())

    for field_name, field_schema in PAYLOAD_INDEXES.items():
        if field_name in existing_indexes:
            continue

        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_schema,
            wait=True,
        )


def _validate_collection(
    *,
    client: QdrantClient,
    collection_name: str,
    expected_vector_size: int,
) -> None:
    collection_info = client.get_collection(collection_name)
    vectors_config = collection_info.config.params.vectors

    if not isinstance(vectors_config, dict):
        raise RuntimeError(
            f"Collection {collection_name!r} uses an unnamed vector. "
            f"Expected named vector {DENSE_VECTOR_NAME!r}."
        )

    dense_config = vectors_config.get(DENSE_VECTOR_NAME)

    if dense_config is None:
        raise RuntimeError(
            f"Collection {collection_name!r} does not contain "
            f"vector {DENSE_VECTOR_NAME!r}."
        )

    if dense_config.size != expected_vector_size:
        raise RuntimeError(
            "Qdrant vector size mismatch: "
            f"collection={dense_config.size}, "
            f"settings={expected_vector_size}. "
            "Create a new versioned collection instead of reusing "
            "the current one."
        )

    if dense_config.distance != models.Distance.COSINE:
        raise RuntimeError(
            "Qdrant distance mismatch: "
            f"expected={models.Distance.COSINE}, "
            f"actual={dense_config.distance}."
        )