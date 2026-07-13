import math

import pytest

from app.services.embedding_service import HashEmbeddingService


@pytest.mark.asyncio
async def test_hash_embeddings_are_deterministic_and_normalized() -> None:
    service = HashEmbeddingService(64)
    first = await service.embed_query("артериальная гипертензия")
    second = await service.embed_query("артериальная гипертензия")
    assert first == second
    assert len(first) == 64
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


@pytest.mark.asyncio
async def test_related_text_has_higher_dot_product() -> None:
    service = HashEmbeddingService(256)
    query = await service.embed_query("лечение гипертензии препаратами")
    related, unrelated = await service.embed_documents(
        ["препараты для лечения гипертензии", "строение костей кисти"]
    )
    def dot(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert dot(query, related) > dot(query, unrelated)
