CREATE VIRTUAL TABLE document_chunks_cjk_fts USING fts5(
    content,
    section_path,
    content='document_chunks',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE TRIGGER document_chunks_cjk_fts_insert
AFTER INSERT ON document_chunks BEGIN
    INSERT INTO document_chunks_cjk_fts(rowid, content, section_path)
    VALUES (new.rowid, new.content, new.section_path);
END;

CREATE TRIGGER document_chunks_cjk_fts_delete
AFTER DELETE ON document_chunks BEGIN
    INSERT INTO document_chunks_cjk_fts(
        document_chunks_cjk_fts, rowid, content, section_path
    ) VALUES ('delete', old.rowid, old.content, old.section_path);
END;

CREATE TRIGGER document_chunks_cjk_fts_update
AFTER UPDATE ON document_chunks BEGIN
    INSERT INTO document_chunks_cjk_fts(
        document_chunks_cjk_fts, rowid, content, section_path
    ) VALUES ('delete', old.rowid, old.content, old.section_path);
    INSERT INTO document_chunks_cjk_fts(rowid, content, section_path)
    VALUES (new.rowid, new.content, new.section_path);
END;

INSERT INTO document_chunks_cjk_fts(document_chunks_cjk_fts)
VALUES ('rebuild');
