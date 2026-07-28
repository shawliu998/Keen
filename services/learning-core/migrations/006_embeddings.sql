CREATE TABLE embedding_models (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK (length(provider) > 0),
    model TEXT NOT NULL CHECK (length(model) > 0),
    version TEXT NOT NULL CHECK (length(version) > 0),
    dimensions INTEGER NOT NULL CHECK (dimensions BETWEEN 1 AND 8192),
    created_at TEXT NOT NULL,
    UNIQUE(provider, model, version, dimensions)
);

CREATE TABLE chunk_embeddings (
    chunk_id TEXT NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL REFERENCES embedding_models(id) ON DELETE CASCADE,
    dimensions INTEGER NOT NULL CHECK (dimensions BETWEEN 1 AND 8192),
    embedding BLOB NOT NULL CHECK (
        typeof(embedding) = 'blob' AND length(embedding) = dimensions * 4
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chunk_id, model_id)
);

CREATE TABLE document_embedding_state (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL REFERENCES embedding_models(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'embedding', 'ready', 'failed')
    ),
    expected_chunk_count INTEGER NOT NULL DEFAULT 0
        CHECK (expected_chunk_count >= 0),
    embedded_chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (
        embedded_chunk_count >= 0
        AND embedded_chunk_count <= expected_chunk_count
    ),
    error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (document_id, model_id)
);

CREATE INDEX chunk_embeddings_model_idx
ON chunk_embeddings(model_id, chunk_id);

CREATE INDEX document_embedding_state_status_idx
ON document_embedding_state(model_id, status, document_id);

CREATE TRIGGER chunk_embeddings_model_dimensions_insert
BEFORE INSERT ON chunk_embeddings BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM embedding_models
        WHERE id = new.model_id AND dimensions = new.dimensions
    ) THEN RAISE(ABORT, 'embedding dimensions do not match model registry') END;
END;

CREATE TRIGGER chunk_embeddings_model_dimensions_update
BEFORE UPDATE OF model_id, dimensions, embedding ON chunk_embeddings BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM embedding_models
        WHERE id = new.model_id AND dimensions = new.dimensions
    ) THEN RAISE(ABORT, 'embedding dimensions do not match model registry') END;
END;

CREATE TRIGGER IF NOT EXISTS embedding_models_identity_immutable
BEFORE UPDATE ON embedding_models BEGIN
    SELECT RAISE(ABORT, 'embedding model identity is immutable');
END;
