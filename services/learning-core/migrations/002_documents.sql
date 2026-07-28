CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    extension TEXT NOT NULL CHECK (extension IN ('.pdf', '.md', '.txt')),
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'parsing', 'chunking', 'indexed', 'failed')
    ),
    page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE document_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    storage_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    parser_version TEXT NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
    created_at TEXT NOT NULL,
    UNIQUE(document_id, version_number)
);

CREATE TABLE document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    section_path TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL CHECK (length(content) > 0),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    text_location TEXT NOT NULL CHECK (json_valid(text_location)),
    parser_version TEXT NOT NULL,
    embedding_version TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(version_id, ordinal)
);

CREATE TABLE document_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL CHECK (
        to_status IN ('queued', 'parsing', 'chunking', 'indexed', 'failed')
    ),
    detail TEXT,
    occurred_at TEXT NOT NULL
);

CREATE INDEX documents_course_status_idx ON documents(course_id, status);
CREATE INDEX documents_created_idx ON documents(created_at, id);
CREATE INDEX document_versions_document_idx
    ON document_versions(document_id, version_number DESC);
CREATE INDEX document_versions_hash_idx ON document_versions(content_hash);
CREATE INDEX document_chunks_document_idx
    ON document_chunks(document_id, ordinal);
CREATE INDEX document_chunks_version_page_idx
    ON document_chunks(version_id, page_number, ordinal);
CREATE INDEX document_status_events_document_idx
    ON document_status_events(document_id, occurred_at, id);

CREATE VIRTUAL TABLE document_chunks_fts USING fts5(
    content,
    section_path,
    content='document_chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER document_chunks_fts_insert AFTER INSERT ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(rowid, content, section_path)
    VALUES (new.rowid, new.content, new.section_path);
END;

CREATE TRIGGER document_chunks_fts_delete AFTER DELETE ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, content, section_path)
    VALUES ('delete', old.rowid, old.content, old.section_path);
END;

CREATE TRIGGER document_chunks_fts_update AFTER UPDATE ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, content, section_path)
    VALUES ('delete', old.rowid, old.content, old.section_path);
    INSERT INTO document_chunks_fts(rowid, content, section_path)
    VALUES (new.rowid, new.content, new.section_path);
END;
