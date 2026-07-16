BEGIN;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'uploaded',
    source_url TEXT,
    original_filename VARCHAR(500),
    storage_path TEXT,
    mime_type VARCHAR(255),
    size_bytes BIGINT,
    checksum_sha256 VARCHAR(64),
    content_text TEXT NOT NULL,
    specialty VARCHAR(100),
    lecture_date DATE,
    language VARCHAR(16) NOT NULL DEFAULT 'ru',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT documents_source_type_check CHECK (source_type IN ('pdf', 'url', 'text')),
    CONSTRAINT documents_status_check CHECK (status IN ('uploaded', 'processing', 'ready', 'failed')),
    CONSTRAINT documents_source_url_check CHECK (
        (source_type = 'url' AND source_url IS NOT NULL AND BTRIM(source_url) <> '')
        OR (source_type <> 'url' AND source_url IS NULL)
    ),
    CONSTRAINT documents_content_text_check CHECK (BTRIM(content_text) <> ''),
    CONSTRAINT documents_size_bytes_check CHECK (size_bytes IS NULL OR size_bytes >= 0),
    CONSTRAINT documents_checksum_sha256_check CHECK (
        checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT documents_metadata_object_check CHECK (JSONB_TYPEOF(metadata) = 'object'),
    CONSTRAINT documents_chunk_count_check CHECK (chunk_count >= 0),
    CONSTRAINT documents_error_status_check CHECK (
        (status = 'failed' AND error_message IS NOT NULL AND BTRIM(error_message) <> '')
        OR (status <> 'failed' AND error_message IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS index_jobs (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    chunk_size INTEGER NOT NULL,
    chunk_overlap INTEGER NOT NULL,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT index_jobs_status_check CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT index_jobs_progress_check CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT index_jobs_chunking_check CHECK (
        chunk_size > 0 AND chunk_overlap >= 0 AND chunk_overlap < chunk_size
    ),
    CONSTRAINT index_jobs_result_object_check CHECK (JSONB_TYPEOF(result) = 'object')
);

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    rating SMALLINT NOT NULL,
    comment TEXT,
    document_ids UUID[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT feedback_rating_check CHECK (rating IN (-1, 1)),
    CONSTRAINT feedback_metadata_object_check CHECK (JSONB_TYPEOF(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_status_created_at ON documents (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents (source_type);
CREATE INDEX IF NOT EXISTS idx_documents_specialty ON documents (specialty) WHERE specialty IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_index_jobs_document_created ON index_jobs (document_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_index_jobs_status_created ON index_jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at DESC);

CREATE OR REPLACE FUNCTION set_row_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS documents_set_updated_at ON documents;
CREATE TRIGGER documents_set_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW EXECUTE FUNCTION set_row_updated_at();

DROP TRIGGER IF EXISTS index_jobs_set_updated_at ON index_jobs;
CREATE TRIGGER index_jobs_set_updated_at
BEFORE UPDATE ON index_jobs
FOR EACH ROW EXECUTE FUNCTION set_row_updated_at();

COMMIT;
