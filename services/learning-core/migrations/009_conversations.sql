CREATE TABLE conversations (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
    mode TEXT NOT NULL DEFAULT 'ask'
        CHECK (mode IN ('ask', 'teach', 'study', 'review', 'plan')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    CHECK ((status = 'archived') = (archived_at IS NOT NULL))
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    conversation_id TEXT NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'streaming', 'completed', 'failed', 'cancelled', 'interrupted')
    ),
    content TEXT NOT NULL DEFAULT '',
    model_provider TEXT,
    model_name TEXT,
    prompt_version TEXT,
    error_code TEXT,
    error_detail TEXT,
    idempotency_key TEXT CHECK (
        idempotency_key IS NULL OR length(idempotency_key) BETWEEN 1 AND 256
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (conversation_id, sequence),
    UNIQUE (conversation_id, idempotency_key),
    CHECK (status != 'completed' OR completed_at IS NOT NULL)
);

CREATE TABLE message_citations (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    chunk_id TEXT REFERENCES document_chunks(id) ON DELETE SET NULL,
    page_number INTEGER CHECK (page_number IS NULL OR page_number > 0),
    quote TEXT NOT NULL CHECK (length(quote) BETWEEN 1 AND 10000),
    metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(metadata_json) AND json_type(metadata_json) = 'object'),
    UNIQUE (message_id, ordinal)
);

CREATE TABLE message_attachments (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 500),
    UNIQUE (message_id, ordinal)
);

CREATE INDEX conversations_updated_idx
ON conversations(status, updated_at DESC, id);

CREATE INDEX messages_conversation_sequence_idx
ON messages(conversation_id, sequence, id);

CREATE INDEX messages_recovery_idx
ON messages(status, updated_at, id)
WHERE status IN ('pending', 'streaming');

CREATE INDEX message_citations_document_idx
ON message_citations(document_id, message_id);

CREATE INDEX message_attachments_document_idx
ON message_attachments(document_id, message_id);

CREATE TRIGGER message_citations_chunk_document_insert
BEFORE INSERT ON message_citations WHEN new.chunk_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM document_chunks
        WHERE id = new.chunk_id AND document_id = new.document_id
    ) THEN RAISE(ABORT, 'citation chunk does not belong to document') END;
END;

CREATE TRIGGER message_citations_chunk_document_update
BEFORE UPDATE OF chunk_id, document_id ON message_citations
WHEN new.chunk_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM document_chunks
        WHERE id = new.chunk_id AND document_id = new.document_id
    ) THEN RAISE(ABORT, 'citation chunk does not belong to document') END;
END;
