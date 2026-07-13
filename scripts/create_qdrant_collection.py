from qdrant_client import QdrantClient

from app.config import settings
from app.qdrant_schema import ensure_qdrant_collection


def main() -> None:
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=10.0,
    )

    try:
        ensure_qdrant_collection(
            client,
            collection_name=settings.qdrant_collection_name,
            vector_size=settings.embedding_dimension,
        )

        collection_info = client.get_collection(
            settings.qdrant_collection_name
        )

        print(
            "Qdrant collection is ready:",
            settings.qdrant_collection_name,
        )
        print("Status:", collection_info.status)
        print(
            "Points:",
            collection_info.points_count,
        )
        print(
            "Payload indexes:",
            sorted(collection_info.payload_schema.keys()),
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()