ALTER TABLE agent_runs
ADD COLUMN course_scope_id TEXT REFERENCES courses(id) ON DELETE RESTRICT;

-- Historical runs inherit the most specific persisted learning context. A study
-- session is authoritative when present; otherwise the conversation course is
-- used. Runs without a course-bound context intentionally remain unscoped.
UPDATE agent_runs
SET course_scope_id = COALESCE(
    (
        SELECT s.course_id
        FROM study_sessions s
        WHERE s.id = agent_runs.study_session_id
    ),
    (
        SELECT c.course_id
        FROM conversations c
        WHERE c.id = agent_runs.conversation_id
    )
);

CREATE INDEX agent_runs_course_scope_idx
ON agent_runs(course_scope_id, created_at, id);

CREATE TRIGGER agent_runs_course_scope_insert
BEFORE INSERT ON agent_runs BEGIN
    SELECT CASE WHEN new.study_session_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_sessions s
        WHERE s.id = new.study_session_id
          AND s.course_id = new.course_scope_id
    ) THEN RAISE(ABORT, 'agent run course scope does not match study session') END;
    SELECT CASE WHEN new.study_session_id IS NULL
        AND new.conversation_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = new.conversation_id
              AND c.course_id IS new.course_scope_id
        )
        THEN RAISE(ABORT, 'agent run course scope does not match conversation') END;
    SELECT CASE WHEN new.study_session_id IS NULL
        AND new.conversation_id IS NULL
        AND new.course_scope_id IS NOT NULL
        THEN RAISE(ABORT, 'agent run course scope requires learning context') END;
END;

CREATE TRIGGER agent_runs_course_scope_update
BEFORE UPDATE OF course_scope_id, conversation_id, study_session_id ON agent_runs BEGIN
    SELECT CASE WHEN new.course_scope_id IS NOT old.course_scope_id
        THEN RAISE(ABORT, 'agent run course scope is immutable') END;
    SELECT CASE WHEN new.study_session_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_sessions s
        WHERE s.id = new.study_session_id
          AND s.course_id = new.course_scope_id
    ) THEN RAISE(ABORT, 'agent run course scope does not match study session') END;
    SELECT CASE WHEN new.study_session_id IS NULL
        AND new.conversation_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = new.conversation_id
              AND c.course_id IS new.course_scope_id
        )
        THEN RAISE(ABORT, 'agent run course scope does not match conversation') END;
    -- A referenced conversation or study session may later be deleted through
    -- its existing ON DELETE SET NULL relationship. Keep the immutable course
    -- scope as historical audit evidence even when both live contexts are gone.
END;
