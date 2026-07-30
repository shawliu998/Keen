ALTER TABLE conversations ADD COLUMN source_scope_kind TEXT
    CHECK (source_scope_kind IS NULL OR source_scope_kind IN ('all_indexed', 'course'));
ALTER TABLE conversations ADD COLUMN create_payload_fingerprint TEXT
    CHECK (
        create_payload_fingerprint IS NULL OR (
            length(create_payload_fingerprint) = 64
            AND create_payload_fingerprint NOT GLOB '*[^0-9a-f]*'
        )
    );

ALTER TABLE messages ADD COLUMN reply_to_message_id TEXT
    REFERENCES messages(id) ON DELETE RESTRICT;
ALTER TABLE messages ADD COLUMN source_scope_kind TEXT
    CHECK (source_scope_kind IS NULL OR source_scope_kind IN ('all_indexed', 'course'));
ALTER TABLE messages ADD COLUMN source_course_id TEXT
    REFERENCES courses(id) ON DELETE RESTRICT;
ALTER TABLE messages ADD COLUMN retrieval_limit INTEGER
    CHECK (retrieval_limit IS NULL OR retrieval_limit BETWEEN 6 AND 10);
ALTER TABLE messages ADD COLUMN started_at TEXT;
ALTER TABLE messages ADD COLUMN finished_at TEXT;
ALTER TABLE messages ADD COLUMN cancel_idempotency_key TEXT
    CHECK (
        cancel_idempotency_key IS NULL OR
        length(cancel_idempotency_key) BETWEEN 1 AND 256
    );

ALTER TABLE message_citations ADD COLUMN source_index INTEGER
    CHECK (source_index IS NULL OR source_index > 0);
ALTER TABLE message_citations ADD COLUMN document_version_id TEXT
    REFERENCES document_versions(id) ON DELETE RESTRICT;
ALTER TABLE message_citations ADD COLUMN chunk_content_hash TEXT
    CHECK (
        chunk_content_hash IS NULL OR (
            length(chunk_content_hash) = 64
            AND chunk_content_hash NOT GLOB '*[^0-9a-f]*'
        )
    );
ALTER TABLE message_citations ADD COLUMN document_name_snapshot TEXT
    CHECK (
        document_name_snapshot IS NULL OR
        length(document_name_snapshot) BETWEEN 1 AND 500
    );
ALTER TABLE message_citations ADD COLUMN section_path_json TEXT
    CHECK (
        section_path_json IS NULL OR (
            json_valid(section_path_json) AND json_type(section_path_json) = 'array'
        )
    );
ALTER TABLE message_citations ADD COLUMN geometry_json TEXT
    CHECK (
        geometry_json IS NULL OR (
            json_valid(geometry_json) AND json_type(geometry_json) = 'object'
        )
    );

CREATE UNIQUE INDEX message_citations_message_source_idx
ON message_citations(message_id, source_index)
WHERE source_index IS NOT NULL;

-- Migration 009 rows remain nullable. Every row created after this migration
-- must declare the source boundary and immutable create payload identity.
CREATE TRIGGER conversations_durable_insert
BEFORE INSERT ON conversations BEGIN
    SELECT CASE WHEN new.source_scope_kind IS NULL
        THEN RAISE(ABORT, 'conversation source scope is required') END;
    SELECT CASE WHEN new.create_payload_fingerprint IS NULL
        THEN RAISE(ABORT, 'conversation create fingerprint is required') END;
    SELECT CASE WHEN
        (new.source_scope_kind = 'all_indexed' AND new.course_id IS NOT NULL)
        OR (new.source_scope_kind = 'course' AND new.course_id IS NULL)
        THEN RAISE(ABORT, 'conversation source scope is inconsistent') END;
END;

CREATE TRIGGER conversations_durable_update
BEFORE UPDATE OF course_id, source_scope_kind, create_payload_fingerprint
ON conversations
WHEN old.source_scope_kind IS NOT NULL BEGIN
    SELECT CASE WHEN new.source_scope_kind IS NULL
        OR new.create_payload_fingerprint IS NULL
        OR (new.source_scope_kind = 'all_indexed' AND new.course_id IS NOT NULL)
        OR (new.source_scope_kind = 'course' AND new.course_id IS NULL)
        THEN RAISE(ABORT, 'conversation source scope is inconsistent') END;
END;

CREATE TRIGGER messages_durable_insert
BEFORE INSERT ON messages BEGIN
    SELECT CASE WHEN new.source_scope_kind IS NULL
        THEN RAISE(ABORT, 'message source scope is required') END;
    SELECT CASE WHEN
        (new.source_scope_kind = 'all_indexed' AND new.source_course_id IS NOT NULL)
        OR (new.source_scope_kind = 'course' AND new.source_course_id IS NULL)
        THEN RAISE(ABORT, 'message source scope is inconsistent') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = new.conversation_id
          AND c.source_scope_kind = new.source_scope_kind
          AND c.course_id IS new.source_course_id
    ) THEN RAISE(ABORT, 'message source scope does not match conversation') END;
    SELECT CASE WHEN new.reply_to_message_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM messages parent
        WHERE parent.id = new.reply_to_message_id
          AND parent.conversation_id = new.conversation_id
          AND parent.role = 'user'
          AND parent.sequence < new.sequence
    ) THEN RAISE(ABORT, 'message reply target is invalid') END;
    SELECT CASE WHEN new.role = 'assistant' AND (
        new.reply_to_message_id IS NULL OR new.retrieval_limit IS NULL
    ) THEN RAISE(ABORT, 'assistant message requires reply and retrieval limit') END;
    SELECT CASE WHEN new.role = 'user' AND (
        new.reply_to_message_id IS NOT NULL OR new.retrieval_limit IS NOT NULL
    ) THEN RAISE(ABORT, 'user message cannot carry reply or retrieval limit') END;
    SELECT CASE WHEN new.role IN ('system', 'tool') AND (
        new.reply_to_message_id IS NOT NULL OR new.retrieval_limit IS NOT NULL
    ) THEN RAISE(ABORT, 'non-turn message cannot carry reply or retrieval limit') END;
    SELECT CASE WHEN new.cancel_idempotency_key IS NOT NULL
        AND new.status != 'cancelled'
        THEN RAISE(ABORT, 'cancel key requires cancelled status') END;
END;

CREATE TRIGGER messages_durable_update
BEFORE UPDATE OF conversation_id, sequence, role, reply_to_message_id,
                 source_scope_kind, source_course_id, retrieval_limit,
                 cancel_idempotency_key, status
ON messages
WHEN old.source_scope_kind IS NOT NULL OR new.source_scope_kind IS NOT NULL BEGIN
    SELECT CASE WHEN new.source_scope_kind IS NULL
        OR (new.source_scope_kind = 'all_indexed' AND new.source_course_id IS NOT NULL)
        OR (new.source_scope_kind = 'course' AND new.source_course_id IS NULL)
        THEN RAISE(ABORT, 'message source scope is inconsistent') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = new.conversation_id
          AND c.source_scope_kind = new.source_scope_kind
          AND c.course_id IS new.source_course_id
    ) THEN RAISE(ABORT, 'message source scope does not match conversation') END;
    SELECT CASE WHEN new.reply_to_message_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM messages parent
        WHERE parent.id = new.reply_to_message_id
          AND parent.conversation_id = new.conversation_id
          AND parent.role = 'user'
          AND parent.sequence < new.sequence
    ) THEN RAISE(ABORT, 'message reply target is invalid') END;
    SELECT CASE WHEN new.role = 'assistant' AND (
        new.reply_to_message_id IS NULL OR new.retrieval_limit IS NULL
    ) THEN RAISE(ABORT, 'assistant message requires reply and retrieval limit') END;
    SELECT CASE WHEN new.role = 'user' AND (
        new.reply_to_message_id IS NOT NULL OR new.retrieval_limit IS NOT NULL
    ) THEN RAISE(ABORT, 'user message cannot carry reply or retrieval limit') END;
    SELECT CASE WHEN new.role IN ('system', 'tool') AND (
        new.reply_to_message_id IS NOT NULL OR new.retrieval_limit IS NOT NULL
    ) THEN RAISE(ABORT, 'non-turn message cannot carry reply or retrieval limit') END;
    SELECT CASE WHEN new.cancel_idempotency_key IS NOT NULL
        AND new.status != 'cancelled'
        THEN RAISE(ABORT, 'cancel key requires cancelled status') END;
END;

CREATE TRIGGER message_citations_durable_insert
BEFORE INSERT ON message_citations BEGIN
    SELECT CASE WHEN new.source_index IS NULL
        OR new.chunk_id IS NULL
        OR new.document_version_id IS NULL
        OR new.chunk_content_hash IS NULL
        OR new.document_name_snapshot IS NULL
        OR new.section_path_json IS NULL
        THEN RAISE(ABORT, 'citation durable evidence is required') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM document_chunks chunk
        JOIN document_versions version ON version.id = chunk.version_id
        WHERE chunk.id = new.chunk_id
          AND chunk.document_id = new.document_id
          AND chunk.version_id = new.document_version_id
          AND chunk.content_hash = new.chunk_content_hash
          AND chunk.page_number = new.page_number
          AND version.document_id = new.document_id
    ) THEN RAISE(ABORT, 'citation evidence does not match stored chunk') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM messages message
        JOIN conversations conversation ON conversation.id = message.conversation_id
        JOIN documents document ON document.id = new.document_id
        WHERE message.id = new.message_id
          AND message.role = 'assistant'
          AND document.name = new.document_name_snapshot
          AND (
              message.source_scope_kind = 'all_indexed'
              OR EXISTS (
                  SELECT 1 FROM course_documents cd
                  WHERE cd.course_id = message.source_course_id
                    AND cd.document_id = new.document_id
              )
          )
    ) THEN RAISE(ABORT, 'citation evidence is outside message source scope') END;
END;

CREATE TRIGGER message_citations_durable_update
BEFORE UPDATE ON message_citations BEGIN
    SELECT RAISE(ABORT, 'durable citation evidence is immutable');
END;
