BEGIN;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS original_filename VARCHAR(500);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_path TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS mime_type VARCHAR(255);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes BIGINT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS checksum_sha256 VARCHAR(64);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_text TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS language VARCHAR(16) NOT NULL DEFAULT 'ru';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message TEXT;

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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    document_ids UUID[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_index_jobs_document_created ON index_jobs (document_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_index_jobs_status_created ON index_jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at DESC);

DROP TRIGGER IF EXISTS index_jobs_set_updated_at ON index_jobs;
CREATE TRIGGER index_jobs_set_updated_at
BEFORE UPDATE ON index_jobs
FOR EACH ROW EXECUTE FUNCTION set_row_updated_at();

COMMIT;
