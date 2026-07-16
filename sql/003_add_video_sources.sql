BEGIN;

ALTER TABLE documents
    ALTER COLUMN content_text DROP NOT NULL;

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_source_type_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_source_type_check
    CHECK (source_type IN ('pdf', 'url', 'text', 'video'));

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_content_text_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_content_text_check
    CHECK (
        (source_type = 'video' AND (content_text IS NULL OR BTRIM(content_text) <> ''))
        OR (source_type <> 'video' AND content_text IS NOT NULL AND BTRIM(content_text) <> '')
    );

COMMIT;
