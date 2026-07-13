import asyncio
from uuid import UUID

from app.repositories.document_repository import (
    DocumentRepository,
    create_database_pool,
)
from app.schemas import (
    DocumentIn,
    DocumentStatus,
    SourceType,
)


async def main() -> None:
    pool = await create_database_pool()
    repository = DocumentRepository(pool)

    created_document_id: UUID | None = None

    try:
        print(
            "PostgreSQL доступен:",
            await repository.ping(),
        )

        created_document = await repository.create(
            DocumentIn(
                title="Тестовый медицинский материал",
                source_type=SourceType.TEXT,
                raw_text=(
                    "Метформин снижает продукцию глюкозы "
                    "в печени и повышает чувствительность "
                    "тканей к инсулину."
                ),
                specialty="эндокринология",
                metadata={
                    "language": "ru",
                    "is_test": True,
                },
            )
        )

        created_document_id = created_document.id

        print("\n1. Документ создан:")
        print(
            created_document.model_dump(
                mode="json"
            )
        )

        loaded_document = await repository.get_by_id(
            created_document.id
        )

        assert loaded_document is not None
        assert loaded_document.id == created_document.id
        assert loaded_document.status == DocumentStatus.UPLOADED

        print("\n2. Документ прочитан:")
        print(
            loaded_document.model_dump(
                mode="json"
            )
        )

        content = await repository.get_content(
            created_document.id
        )

        assert content is not None
        assert "Метформин" in content

        print("\n3. Полный текст:")
        print(content)

        processing_document = await repository.update_status(
            created_document.id,
            DocumentStatus.PROCESSING,
        )

        assert processing_document is not None
        assert (
            processing_document.status
            == DocumentStatus.PROCESSING
        )

        print("\n4. Статус после начала обработки:")
        print(processing_document.status)

        document_with_chunks = (
            await repository.update_chunk_count(
                created_document.id,
                3,
            )
        )

        assert document_with_chunks is not None
        assert document_with_chunks.chunk_count == 3

        print("\n5. Количество chunks:")
        print(document_with_chunks.chunk_count)

        document_with_metadata = (
            await repository.merge_metadata(
                created_document.id,
                {
                    "parser": "plain_text",
                    "processed": True,
                },
            )
        )

        assert document_with_metadata is not None
        assert (
            document_with_metadata.metadata["language"]
            == "ru"
        )
        assert (
            document_with_metadata.metadata["parser"]
            == "plain_text"
        )

        print("\n6. Metadata после объединения:")
        print(document_with_metadata.metadata)

        ready_document = await repository.update_status(
            created_document.id,
            DocumentStatus.READY,
        )

        assert ready_document is not None
        assert ready_document.status == DocumentStatus.READY

        print("\n7. Финальный статус:")
        print(ready_document.status)

        documents = await repository.list_documents(
            specialty="эндокринология",
            status=DocumentStatus.READY,
        )

        assert any(
            document.id == created_document.id
            for document in documents
        )

        print("\n8. Документов найдено по фильтрам:")
        print(len(documents))

        total_count = await repository.count_documents()

        ready_count = await repository.count_documents(
            status=DocumentStatus.READY
        )

        print("\n9. Количество документов:")
        print("Всего:", total_count)
        print("В статусе ready:", ready_count)

    finally:
        if created_document_id is not None:
            deleted = await repository.delete(
                created_document_id
            )

            print("\n10. Тестовый документ удалён:")
            print(deleted)

        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())