from __future__ import annotations

import asyncio

from qdrant_client import AsyncQdrantClient

from app.config import settings
from app.repositories.vector_repository import VectorRepository


async def main() -> None:
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.get_qdrant_api_key(),
        timeout=settings.qdrant_timeout_seconds,
    )
    try:
        repository = VectorRepository(
            client,
            collection_name=settings.qdrant_collection_name,
            vector_size=settings.embedding_dimension,
            upsert_batch_size=settings.qdrant_upsert_batch_size,
        )
        await repository.ensure_collection()
        print(
            f"Qdrant collection {settings.qdrant_collection_name!r} is ready "
            f"with dimension={settings.embedding_dimension}"
        )
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
