CREATE TABLE document_index_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (
        status IN (
            'queued', 'running', 'cancel_requested', 'cancelled',
            'completed', 'failed', 'interrupted'
        )
    ),
    stage TEXT NOT NULL CHECK (
        stage IN (
            'queued', 'validating', 'stored', 'parsing', 'chunking',
            'lexical_indexing', 'embedding', 'finalizing'
        )
    ),
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    worker_generation TEXT
);

CREATE INDEX document_index_jobs_document_created_idx
ON document_index_jobs(document_id, created_at DESC, id DESC);

CREATE INDEX document_index_jobs_status_created_idx
ON document_index_jobs(status, created_at, id);

CREATE UNIQUE INDEX document_index_jobs_one_active_per_document_idx
ON document_index_jobs(document_id)
WHERE status IN ('queued', 'running', 'cancel_requested');

INSERT INTO document_index_jobs (
    id, document_id, status, stage, progress, cancel_requested, error,
    created_at, updated_at, started_at, finished_at, worker_generation
)
SELECT
    'job-migrated-' || d.id,
    d.id,
    CASE
        WHEN d.status = 'indexed' THEN 'completed'
        WHEN d.status = 'failed' THEN 'failed'
        ELSE 'interrupted'
    END,
    CASE WHEN d.status = 'indexed' THEN 'finalizing' ELSE 'parsing' END,
    CASE WHEN d.status = 'indexed' THEN 100 ELSE 0 END,
    0,
    CASE
        WHEN d.status IN ('queued', 'parsing', 'chunking')
            THEN 'indexing was interrupted before persistent jobs were enabled'
        ELSE d.error
    END,
    d.created_at,
    d.updated_at,
    NULL,
    d.updated_at,
    NULL
FROM documents d;
