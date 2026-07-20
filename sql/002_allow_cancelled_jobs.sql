BEGIN;

ALTER TABLE index_jobs
DROP CONSTRAINT IF EXISTS index_jobs_status_check;

ALTER TABLE index_jobs
ADD CONSTRAINT index_jobs_status_check CHECK (
    status IN ('pending', 'running', 'completed', 'failed', 'cancelled')
);

COMMIT;
