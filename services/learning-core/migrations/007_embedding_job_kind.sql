ALTER TABLE document_index_jobs
ADD COLUMN operation TEXT NOT NULL DEFAULT 'full_index'
CHECK (operation IN ('full_index', 'embedding_reindex'));

ALTER TABLE document_index_jobs
ADD COLUMN embedding_model_id TEXT
REFERENCES embedding_models(id) ON DELETE RESTRICT;

-- Forward-repair databases that applied an earlier v006 during development
-- before the model-registry immutability trigger was added.
CREATE TRIGGER IF NOT EXISTS embedding_models_identity_immutable
BEFORE UPDATE ON embedding_models BEGIN
    SELECT RAISE(ABORT, 'embedding model identity is immutable');
END;

CREATE TABLE embedding_reindex_staging (
    job_id TEXT NOT NULL
        REFERENCES document_index_jobs(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL REFERENCES embedding_models(id) ON DELETE RESTRICT,
    dimensions INTEGER NOT NULL CHECK (dimensions BETWEEN 1 AND 8192),
    embedding BLOB NOT NULL CHECK (
        typeof(embedding) = 'blob' AND length(embedding) = dimensions * 4
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (job_id, chunk_id)
);

CREATE INDEX embedding_reindex_staging_model_idx
ON embedding_reindex_staging(model_id, job_id, chunk_id);

CREATE TRIGGER embedding_reindex_staging_dimensions_insert
BEFORE INSERT ON embedding_reindex_staging BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM embedding_models
        WHERE id = new.model_id AND dimensions = new.dimensions
    ) THEN RAISE(ABORT, 'embedding dimensions do not match model registry') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM document_index_jobs
        WHERE id = new.job_id
          AND operation = 'embedding_reindex'
          AND embedding_model_id = new.model_id
    ) THEN RAISE(ABORT, 'embedding model does not match reindex job') END;
END;

CREATE TRIGGER embedding_reindex_staging_dimensions_update
BEFORE UPDATE OF job_id, model_id, dimensions, embedding
ON embedding_reindex_staging BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM embedding_models
        WHERE id = new.model_id AND dimensions = new.dimensions
    ) THEN RAISE(ABORT, 'embedding dimensions do not match model registry') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM document_index_jobs
        WHERE id = new.job_id
          AND operation = 'embedding_reindex'
          AND embedding_model_id = new.model_id
    ) THEN RAISE(ABORT, 'embedding model does not match reindex job') END;
END;

CREATE TRIGGER document_index_jobs_embedding_target_insert
BEFORE INSERT ON document_index_jobs BEGIN
    SELECT CASE
        WHEN new.operation = 'full_index' AND new.embedding_model_id IS NOT NULL
            THEN RAISE(ABORT, 'full index jobs cannot pin an embedding model')
        WHEN new.operation = 'embedding_reindex'
             AND new.embedding_model_id IS NULL
            THEN RAISE(ABORT, 'embedding reindex jobs require a model')
    END;
END;

CREATE TRIGGER document_index_jobs_embedding_target_update
BEFORE UPDATE OF operation, embedding_model_id ON document_index_jobs BEGIN
    SELECT CASE
        WHEN new.operation = 'full_index' AND new.embedding_model_id IS NOT NULL
            THEN RAISE(ABORT, 'full index jobs cannot pin an embedding model')
        WHEN new.operation = 'embedding_reindex'
             AND new.embedding_model_id IS NULL
            THEN RAISE(ABORT, 'embedding reindex jobs require a model')
    END;
END;
