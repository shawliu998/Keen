CREATE TABLE study_plan_proposals (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    run_id TEXT NOT NULL UNIQUE REFERENCES agent_runs(id) ON DELETE RESTRICT,
    validated_artifact_id TEXT NOT NULL UNIQUE
        CHECK (length(validated_artifact_id) BETWEEN 1 AND 128),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    study_session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    base_plan_id TEXT NOT NULL REFERENCES study_plan_versions(id) ON DELETE RESTRICT,
    base_plan_version INTEGER NOT NULL CHECK (base_plan_version > 0),
    base_session_revision INTEGER NOT NULL CHECK (base_session_revision >= 0),
    trigger_event_ids_json TEXT NOT NULL DEFAULT '[]'
        CHECK (
            json_valid(trigger_event_ids_json)
            AND json_type(trigger_event_ids_json) = 'array'
        ),
    proposal_json TEXT NOT NULL
        CHECK (json_valid(proposal_json) AND json_type(proposal_json) = 'object'),
    reason_json TEXT NOT NULL
        CHECK (json_valid(reason_json) AND json_type(reason_json) = 'object'),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'accepted', 'rejected', 'invalidated', 'undone')),
    accepted_plan_version INTEGER CHECK (accepted_plan_version > base_plan_version),
    undo_plan_version INTEGER CHECK (
        undo_plan_version IS NULL
        OR (
            accepted_plan_version IS NOT NULL
            AND undo_plan_version > accepted_plan_version
        )
    ),
    undo_until TEXT,
    decision_idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(decision_idempotency_key) BETWEEN 16 AND 128),
    undo_idempotency_key TEXT UNIQUE
        CHECK (
            undo_idempotency_key IS NULL
            OR length(undo_idempotency_key) BETWEEN 16 AND 128
        ),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    undone_at TEXT,
    CHECK (
        (status = 'rejected'
            AND accepted_plan_version IS NULL
            AND undo_plan_version IS NULL
            AND undo_until IS NULL
            AND resolved_at IS NOT NULL
            AND undone_at IS NULL)
        OR
        (status = 'accepted'
            AND accepted_plan_version IS NOT NULL
            AND undo_plan_version IS NULL
            AND undo_until IS NOT NULL
            AND resolved_at IS NOT NULL
            AND undone_at IS NULL)
        OR
        (status = 'undone'
            AND accepted_plan_version IS NOT NULL
            AND undo_plan_version IS NOT NULL
            AND undo_until IS NOT NULL
            AND resolved_at IS NOT NULL
            AND undone_at IS NOT NULL)
        OR
        (status = 'pending'
            AND accepted_plan_version IS NULL
            AND undo_plan_version IS NULL
            AND undo_until IS NULL
            AND resolved_at IS NULL
            AND undone_at IS NULL)
        OR
        (status = 'invalidated'
            AND resolved_at IS NOT NULL)
    )
);

CREATE INDEX study_plan_proposals_session_idx
ON study_plan_proposals(study_session_id, created_at DESC, id DESC);

CREATE INDEX study_plan_proposals_base_plan_idx
ON study_plan_proposals(base_plan_id, status);

CREATE TRIGGER study_plan_proposals_scope_insert
BEFORE INSERT ON study_plan_proposals BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM study_sessions s
        JOIN study_plan_versions p ON p.session_id = s.id
        JOIN agent_runs r ON r.id = new.run_id
        WHERE s.id = new.study_session_id
          AND s.course_id = new.course_id
          AND p.id = new.base_plan_id
          AND p.version = new.base_plan_version
          AND r.study_session_id = new.study_session_id
          AND r.course_scope_id = new.course_id
    ) THEN RAISE(ABORT, 'study plan proposal scope does not match') END;
END;

CREATE TRIGGER study_plan_proposals_scope_update
BEFORE UPDATE OF
    run_id, course_id, study_session_id, base_plan_id, base_plan_version
ON study_plan_proposals BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM study_sessions s
        JOIN study_plan_versions p ON p.session_id = s.id
        JOIN agent_runs r ON r.id = new.run_id
        WHERE s.id = new.study_session_id
          AND s.course_id = new.course_id
          AND p.id = new.base_plan_id
          AND p.version = new.base_plan_version
          AND r.study_session_id = new.study_session_id
          AND r.course_scope_id = new.course_id
    ) THEN RAISE(ABORT, 'study plan proposal scope does not match') END;
END;

CREATE TRIGGER study_plan_proposals_versions_insert
BEFORE INSERT ON study_plan_proposals
WHEN new.accepted_plan_version IS NOT NULL OR new.undo_plan_version IS NOT NULL BEGIN
    SELECT CASE WHEN new.accepted_plan_version IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_plan_versions
        WHERE session_id = new.study_session_id
          AND version = new.accepted_plan_version
    ) THEN RAISE(ABORT, 'accepted study plan version does not exist') END;
    SELECT CASE WHEN new.undo_plan_version IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_plan_versions
        WHERE session_id = new.study_session_id
          AND version = new.undo_plan_version
    ) THEN RAISE(ABORT, 'undo study plan version does not exist') END;
END;

CREATE TRIGGER study_plan_proposals_versions_update
BEFORE UPDATE OF accepted_plan_version, undo_plan_version
ON study_plan_proposals BEGIN
    SELECT CASE WHEN new.accepted_plan_version IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_plan_versions
        WHERE session_id = new.study_session_id
          AND version = new.accepted_plan_version
    ) THEN RAISE(ABORT, 'accepted study plan version does not exist') END;
    SELECT CASE WHEN new.undo_plan_version IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_plan_versions
        WHERE session_id = new.study_session_id
          AND version = new.undo_plan_version
    ) THEN RAISE(ABORT, 'undo study plan version does not exist') END;
END;
