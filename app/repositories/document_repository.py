from __future__ import annotations

import json
from uuid import UUID, uuid4

import asyncpg

from app.config import Settings, settings
from app.schemas import (
    DocumentIn,
    DocumentOut,
    DocumentStatus,
    SourceType,
)


# Поля, которые разрешено возвращать наружу через DocumentOut.
#
# Здесь намеренно нет:
# - content_text;
# - storage_path;
# - checksum_sha256;
# - других внутренних полей.
_DOCUMENT_SELECT_COLUMNS = """
    id,
    title,
    source_type,
    status,
    source_url,
    specialty,
    lecture_date,
    metadata,
    chunk_count,
    error_message,
    created_at,
    updated_at
"""


async def _configure_connection(
    connection: asyncpg.Connection,
) -> None:
    """
    Настраивает каждое новое соединение PostgreSQL.

    codec — encoder/decoder определённого типа данных.

    Для JSONB:
    - encoder преобразует Python-словарь в JSON-строку;
    - decoder преобразует JSON-строку обратно в Python-словарь.
    """

    await connection.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
        format="text",
    )


async def create_database_pool(
    config: Settings = settings,
) -> asyncpg.Pool:
    """
    Создаёт пул соединений PostgreSQL.

    pool — пул, то есть набор переиспользуемых соединений.
    Новое TCP-соединение не создаётся для каждого запроса API.
    """

    return await asyncpg.create_pool(
        dsn=config.get_database_url(),
        min_size=config.database_pool_min_size,
        max_size=config.database_pool_max_size,
        command_timeout=(
            config.database_command_timeout_seconds
        ),
        init=_configure_connection,
    )


class DocumentRepository:
    """
    Репозиторий таблицы documents.

    Repository отделяет SQL-запросы от сервисов и endpoint-ов.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def _to_document(
        record: asyncpg.Record,
    ) -> DocumentOut:
        """
        Преобразует строку PostgreSQL в Pydantic-модель.
        """

        return DocumentOut.model_validate(dict(record))

    async def ping(self) -> bool:
        """
        Проверяет соединение с PostgreSQL.

        fetchval означает fetch value — получить одно значение.
        """

        result = await self._pool.fetchval("SELECT 1")

        return result == 1

    async def create(
        self,
        document: DocumentIn,
        *,
        original_filename: str | None = None,
        storage_path: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        checksum_sha256: str | None = None,
    ) -> DocumentOut:
        """
        Создаёт документ в PostgreSQL.

        Для text:
            raw_text записывается в content_text.

        Для URL:
            source_url записывается в source_url.

        Для PDF:
            передаются данные загруженного файла.
        """

        document_id = uuid4()

        record = await self._pool.fetchrow(
            f"""
            INSERT INTO documents (
                id,
                title,
                source_type,
                status,
                source_url,
                original_filename,
                storage_path,
                mime_type,
                size_bytes,
                checksum_sha256,
                content_text,
                specialty,
                lecture_date,
                metadata
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                $10,
                $11,
                $12,
                $13,
                $14
            )
            RETURNING {_DOCUMENT_SELECT_COLUMNS}
            """,
            document_id,
            document.title,
            document.source_type.value,
            DocumentStatus.UPLOADED.value,
            (
                str(document.source_url)
                if document.source_url is not None
                else None
            ),
            original_filename,
            storage_path,
            mime_type,
            size_bytes,
            (
                checksum_sha256.lower()
                if checksum_sha256 is not None
                else None
            ),
            document.raw_text,
            document.specialty,
            document.lecture_date,
            document.metadata,
        )

        if record is None:
            raise RuntimeError(
                "PostgreSQL не вернул созданный документ"
            )

        return self._to_document(record)

    async def get_by_id(
        self,
        document_id: UUID,
    ) -> DocumentOut | None:
        """
        Возвращает документ по UUID.

        fetchrow означает fetch row — получить одну строку.
        """

        record = await self._pool.fetchrow(
            f"""
            SELECT {_DOCUMENT_SELECT_COLUMNS}
            FROM documents
            WHERE id = $1
            """,
            document_id,
        )

        if record is None:
            return None

        return self._to_document(record)

    async def get_content(
        self,
        document_id: UUID,
    ) -> str | None:
        """
        Возвращает полный текст документа.

        Этот текст нужен сервису чанкинга, но не возвращается
        в обычном DocumentOut.
        """

        return await self._pool.fetchval(
            """
            SELECT content_text
            FROM documents
            WHERE id = $1
            """,
            document_id,
        )

    async def list_documents(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: DocumentStatus | None = None,
        source_type: SourceType | None = None,
        specialty: str | None = None,
    ) -> list[DocumentOut]:
        """
        Возвращает список документов.

        limit — максимальное количество результатов.
        offset — количество результатов, которые нужно пропустить.
        """

        if not 1 <= limit <= 500:
            raise ValueError(
                "limit должен находиться в диапазоне от 1 до 500"
            )

        if offset < 0:
            raise ValueError(
                "offset не может быть отрицательным"
            )

        conditions: list[str] = []
        arguments: list[object] = []

        if status is not None:
            arguments.append(status.value)
            conditions.append(
                f"status = ${len(arguments)}"
            )

        if source_type is not None:
            arguments.append(source_type.value)
            conditions.append(
                f"source_type = ${len(arguments)}"
            )

        if specialty is not None:
            arguments.append(specialty)
            conditions.append(
                f"specialty = ${len(arguments)}"
            )

        where_clause = ""

        if conditions:
            where_clause = (
                "WHERE " + " AND ".join(conditions)
            )

        arguments.append(limit)
        limit_parameter_number = len(arguments)

        arguments.append(offset)
        offset_parameter_number = len(arguments)

        records = await self._pool.fetch(
            f"""
            SELECT {_DOCUMENT_SELECT_COLUMNS}
            FROM documents
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${limit_parameter_number}
            OFFSET ${offset_parameter_number}
            """,
            *arguments,
        )

        return [
            self._to_document(record)
            for record in records
        ]

    async def count_documents(
        self,
        *,
        status: DocumentStatus | None = None,
    ) -> int:
        """
        Считает количество документов.
        """

        if status is None:
            count = await self._pool.fetchval(
                """
                SELECT COUNT(*)
                FROM documents
                """
            )
        else:
            count = await self._pool.fetchval(
                """
                SELECT COUNT(*)
                FROM documents
                WHERE status = $1
                """,
                status.value,
            )

        return int(count)

    async def update_content(
        self,
        document_id: UUID,
        content_text: str,
    ) -> DocumentOut | None:
        """
        Записывает извлечённый текст документа.

        Это понадобится после парсинга PDF или загрузки страницы.
        """

        normalized_content = content_text.strip()

        if not normalized_content:
            raise ValueError(
                "content_text не может быть пустым"
            )

        record = await self._pool.fetchrow(
            f"""
            UPDATE documents
            SET content_text = $2
            WHERE id = $1
            RETURNING {_DOCUMENT_SELECT_COLUMNS}
            """,
            document_id,
            normalized_content,
        )

        if record is None:
            return None

        return self._to_document(record)

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        *,
        error_message: str | None = None,
    ) -> DocumentOut | None:
        """
        Меняет статус документа.

        Для статуса failed сообщение об ошибке обязательно.
        Для остальных статусов error_message очищается.
        """

        normalized_error: str | None

        if status == DocumentStatus.FAILED:
            if error_message is None or not error_message.strip():
                raise ValueError(
                    "Для статуса failed необходимо указать "
                    "error_message"
                )

            normalized_error = error_message.strip()
        else:
            normalized_error = None

        record = await self._pool.fetchrow(
            f"""
            UPDATE documents
            SET
                status = $2,
                error_message = $3
            WHERE id = $1
            RETURNING {_DOCUMENT_SELECT_COLUMNS}
            """,
            document_id,
            status.value,
            normalized_error,
        )

        if record is None:
            return None

        return self._to_document(record)

    async def update_chunk_count(
        self,
        document_id: UUID,
        chunk_count: int,
    ) -> DocumentOut | None:
        """
        Обновляет количество chunks документа.
        """

        if chunk_count < 0:
            raise ValueError(
                "chunk_count не может быть отрицательным"
            )

        record = await self._pool.fetchrow(
            f"""
            UPDATE documents
            SET chunk_count = $2
            WHERE id = $1
            RETURNING {_DOCUMENT_SELECT_COLUMNS}
            """,
            document_id,
            chunk_count,
        )

        if record is None:
            return None

        return self._to_document(record)

    async def merge_metadata(
        self,
        document_id: UUID,
        metadata: dict[str, object],
    ) -> DocumentOut | None:
        """
        Объединяет новые metadata со старыми.

        Оператор JSONB || объединяет JSON-объекты.
        Значение справа заменяет старое значение при совпадении ключей.
        """

        record = await self._pool.fetchrow(
            f"""
            UPDATE documents
            SET metadata = metadata || $2::jsonb
            WHERE id = $1
            RETURNING {_DOCUMENT_SELECT_COLUMNS}
            """,
            document_id,
            metadata,
        )

        if record is None:
            return None

        return self._to_document(record)

    async def delete(
        self,
        document_id: UUID,
    ) -> bool:
        """
        Удаляет документ.

        True — документ существовал и был удалён.
        False — документ не найден.
        """

        deleted_id = await self._pool.fetchval(
            """
            DELETE FROM documents
            WHERE id = $1
            RETURNING id
            """,
            document_id,
        )

        return deleted_id is not None