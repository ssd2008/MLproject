BEGIN;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,

    title VARCHAR(300) NOT NULL,

    source_type VARCHAR(16) NOT NULL,

    status VARCHAR(16) NOT NULL DEFAULT 'uploaded',

    /*
     * URL исходного документа.
     *
     * Используется только для source_type = 'url'.
     */
    source_url TEXT,

    /*
     * Поля загруженного файла.
     *
     * Для URL и обычного текста обычно будут NULL.
     */
    original_filename VARCHAR(500),
    storage_path TEXT,
    mime_type VARCHAR(255),
    size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),

    /*
     * Извлечённый текст документа.
     *
     * Для source_type = 'text' записывается сразу.
     * Для PDF и URL появляется после извлечения текста.
     */
    content_text TEXT,

    specialty VARCHAR(100),

    lecture_date DATE,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    chunk_count INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,

    /*
     * TIMESTAMPTZ означает timestamp with time zone —
     * временная метка с учётом часового пояса.
     */
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT documents_source_type_check
        CHECK (
            source_type IN ('pdf', 'url', 'text')
        ),

    CONSTRAINT documents_status_check
        CHECK (
            status IN (
                'uploaded',
                'processing',
                'ready',
                'failed'
            )
        ),

    /*
     * URL обязателен только для URL-источника.
     */
    CONSTRAINT documents_source_url_check
        CHECK (
            source_type = 'url'
            OR source_url IS NULL
        ),

    /*
     * Проверяем, что для каждого типа источника
     * присутствуют минимально необходимые данные.
     */
    CONSTRAINT documents_source_payload_check
        CHECK (
            source_type = 'pdf'

            OR (
                source_type = 'url'
                AND source_url IS NOT NULL
                AND BTRIM(source_url) <> ''
            )

            OR (
                source_type = 'text'
                AND content_text IS NOT NULL
                AND BTRIM(content_text) <> ''
            )
        ),

    CONSTRAINT documents_size_bytes_check
        CHECK (
            size_bytes IS NULL
            OR size_bytes >= 0
        ),

    CONSTRAINT documents_checksum_sha256_check
        CHECK (
            checksum_sha256 IS NULL
            OR (
                CHAR_LENGTH(checksum_sha256) = 64
                AND checksum_sha256 ~ '^[0-9a-f]{64}$'
            )
        ),

    CONSTRAINT documents_metadata_object_check
        CHECK (
            JSONB_TYPEOF(metadata) = 'object'
        ),

    CONSTRAINT documents_chunk_count_check
        CHECK (
            chunk_count >= 0
        ),

    /*
     * Если статус failed, описание ошибки обязательно.
     * Для остальных статусов error_message должен быть NULL.
     */
    CONSTRAINT documents_error_status_check
        CHECK (
            (
                status = 'failed'
                AND error_message IS NOT NULL
                AND BTRIM(error_message) <> ''
            )
            OR (
                status <> 'failed'
                AND error_message IS NULL
            )
        )
);


CREATE INDEX IF NOT EXISTS idx_documents_created_at
    ON documents (created_at DESC);


CREATE INDEX IF NOT EXISTS idx_documents_status_created_at
    ON documents (status, created_at DESC);


CREATE INDEX IF NOT EXISTS idx_documents_source_type
    ON documents (source_type);


CREATE INDEX IF NOT EXISTS idx_documents_specialty
    ON documents (specialty)
    WHERE specialty IS NOT NULL;


/*
 * GIN — Generalized Inverted Index.
 *
 * Пригодится для поиска и фильтрации по содержимому JSONB metadata.
 */
CREATE INDEX IF NOT EXISTS idx_documents_metadata
    ON documents
    USING GIN (metadata);


/*
 * PostgreSQL сам обновляет updated_at при любом UPDATE.
 */
CREATE OR REPLACE FUNCTION set_row_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS documents_set_updated_at
    ON documents;


CREATE TRIGGER documents_set_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION set_row_updated_at();


COMMIT;