from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID, uuid4

from qdrant_client import AsyncQdrantClient

from app.config import settings
from app.qdrant_schema import (
    ChunkPayload,
    build_chunk_point_id,
    calculate_content_hash,
)
from app.repositories.vector_repository import (
    VectorChunk,
    VectorRepository,
)


TEST_VECTOR_SIZE = settings.embedding_dimension


def make_vector(
    *,
    primary_index: int,
    secondary_index: int | None = None,
    secondary_value: float = 0.0,
) -> list[float]:
    vector = [0.0] * TEST_VECTOR_SIZE
    vector[primary_index] = 1.0

    if secondary_index is not None:
        vector[secondary_index] = secondary_value

    return vector


def make_chunk(
    *,
    document_id: UUID,
    chunk_index: int,
    text: str,
    vector: list[float],
    specialty: str,
    char_start: int,
) -> VectorChunk:
    content_hash = calculate_content_hash(text)

    payload = ChunkPayload(
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        token_count=max(1, len(text.split())),
        char_start=char_start,
        char_end=char_start + len(text),
        page_start=chunk_index + 1,
        page_end=chunk_index + 1,
        section_title=f"Раздел {chunk_index}",
        document_title="Интеграционный тест Qdrant",
        source_type="pdf",
        specialty=specialty,
        lecture_date=date(2026, 3, 14),
        language="ru",
        content_hash=content_hash,
    )

    return VectorChunk(
        point_id=build_chunk_point_id(
            document_id=document_id,
            chunk_index=chunk_index,
            content_hash=content_hash,
        ),
        vector=vector,
        payload=payload,
    )


async def main() -> None:
    collection_name = (
        f"{settings.qdrant_collection_name}"
        f"_integration_{uuid4().hex[:8]}"
    )

    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=15.0,
    )

    repository = VectorRepository(
        client=client,
        collection_name=collection_name,
        vector_size=TEST_VECTOR_SIZE,
        upsert_batch_size=2,
        scroll_page_size=2,
    )

    document_id = uuid4()
    other_document_id = uuid4()

    chunks = [
        make_chunk(
            document_id=document_id,
            chunk_index=0,
            text=(
                "Артериальная гипертензия определяется "
                "как стойкое повышение артериального давления."
            ),
            vector=make_vector(primary_index=0),
            specialty="cardiology",
            char_start=0,
        ),
        make_chunk(
            document_id=document_id,
            chunk_index=1,
            text=(
                "Для оценки риска учитывают давление, "
                "возраст и сопутствующие заболевания."
            ),
            vector=make_vector(
                primary_index=0,
                secondary_index=1,
                secondary_value=0.15,
            ),
            specialty="cardiology",
            char_start=100,
        ),
        make_chunk(
            document_id=document_id,
            chunk_index=2,
            text=(
                "Лечение включает изменение образа жизни "
                "и антигипертензивную терапию."
            ),
            vector=make_vector(primary_index=1),
            specialty="cardiology",
            char_start=200,
        ),
        make_chunk(
            document_id=other_document_id,
            chunk_index=0,
            text=(
                "Мигрень представляет собой первичную "
                "головную боль."
            ),
            vector=make_vector(primary_index=2),
            specialty="neurology",
            char_start=0,
        ),
    ]

    try:
        try:
            await repository.ping()
        except Exception as exc:
            raise RuntimeError(
                "Qdrant is unavailable at "
                f"{settings.qdrant_url!r}. "
                "Start the Qdrant container and repeat the test."
            ) from exc

        print("[ok] Qdrant connection")

        await repository.ensure_collection()
        await repository.ensure_collection()
        print("[ok] collection creation is idempotent")

        inserted = await repository.upsert_chunks(chunks)
        assert inserted == 4
        print("[ok] four chunks upserted in two batches")

        first_document_count = (
            await repository.count_by_document_id(
                document_id
            )
        )
        assert first_document_count == 3

        other_document_count = (
            await repository.count_by_document_id(
                other_document_id
            )
        )
        assert other_document_count == 1
        print("[ok] count_by_document_id")

        stored_chunks = (
            await repository.get_chunks_by_document(
                document_id,
                with_vectors=True,
            )
        )
        assert [
            chunk.payload.chunk_index
            for chunk in stored_chunks
        ] == [0, 1, 2]

        assert all(
            chunk.vector is not None
            and len(chunk.vector) == TEST_VECTOR_SIZE
            for chunk in stored_chunks
        )
        print("[ok] scroll pagination and chunk ordering")

        neighbor_chunks = (
            await repository.get_neighbor_chunks(
                document_id=document_id,
                chunk_index=1,
                window=1,
            )
        )
        assert [
            chunk.payload.chunk_index
            for chunk in neighbor_chunks
        ] == [0, 1, 2]

        edge_neighbors = (
            await repository.get_neighbor_chunks(
                document_id=document_id,
                chunk_index=0,
                window=1,
            )
        )
        assert [
            chunk.payload.chunk_index
            for chunk in edge_neighbors
        ] == [0, 1]
        print("[ok] neighbor chunk retrieval")

        search_results = await repository.search(
            make_vector(primary_index=0),
            limit=4,
        )
        assert search_results
        assert (
            search_results[0].point_id
            == chunks[0].point_id
        )
        assert (
            search_results[0].payload.document_id
            == document_id
        )
        print("[ok] dense cosine search")

        filtered_results = await repository.search(
            make_vector(primary_index=0),
            limit=10,
            specialty="cardiology",
            source_type="pdf",
            language="ru",
        )
        assert len(filtered_results) == 3
        assert all(
            result.payload.specialty == "cardiology"
            for result in filtered_results
        )
        print("[ok] payload filters")

        other_document_results = await repository.search(
            make_vector(primary_index=2),
            limit=10,
            document_ids=[other_document_id],
        )
        assert len(other_document_results) == 1
        assert (
            other_document_results[0]
            .payload.document_id
            == other_document_id
        )
        print("[ok] document_ids filter")

        repeated_upsert_count = (
            await repository.upsert_chunks([chunks[0]])
        )
        assert repeated_upsert_count == 1
        assert (
            await repository.count_by_document_id(
                document_id
            )
            == 3
        )
        print("[ok] upsert is idempotent by point ID")

        deleted_count = (
            await repository.delete_by_document_id(
                document_id
            )
        )
        assert deleted_count == 3
        assert (
            await repository.count_by_document_id(
                document_id
            )
            == 0
        )
        assert (
            await repository.count_by_document_id(
                other_document_id
            )
            == 1
        )
        print("[ok] delete_by_document_id")

        second_delete_count = (
            await repository.delete_by_document_id(
                document_id
            )
        )
        assert second_delete_count == 0
        print("[ok] repeated deletion is safe")

        print(
            "\nVectorRepository integration test passed."
        )
    finally:
        try:
            if await client.collection_exists(
                collection_name
            ):
                await client.delete_collection(
                    collection_name=collection_name
                )
                print(
                    "[cleanup] temporary collection deleted"
                )
        finally:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
