-- A Level 2 approval stores the exact, validated command separately from the
-- provider-facing (redacted) proposal invocation.  The execution invocation is
-- host-owned and is attached only once the user confirms it.
CREATE TABLE level2_approval_actions (
    approval_id TEXT PRIMARY KEY REFERENCES approval_requests(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL CHECK (tool_name = 'complete_study_task'),
    canonical_arguments_json TEXT NOT NULL
        CHECK (json_valid(canonical_arguments_json) AND json_type(canonical_arguments_json) = 'object'),
    arguments_hash TEXT NOT NULL CHECK (length(arguments_hash) = 64),
    execution_invocation_id TEXT UNIQUE REFERENCES tool_invocations(id) ON DELETE RESTRICT,
    resolution_kind TEXT CHECK (resolution_kind IN ('confirm', 'reject')),
    resolution_idempotency_key TEXT CHECK (
        resolution_idempotency_key IS NULL
        OR length(resolution_idempotency_key) BETWEEN 1 AND 256
    ),
    created_at TEXT NOT NULL,
    CHECK ((resolution_kind IS NULL) = (resolution_idempotency_key IS NULL)),
    CHECK (execution_invocation_id IS NULL OR resolution_kind = 'confirm')
);

CREATE INDEX level2_approval_actions_run_idx ON level2_approval_actions(run_id, approval_id);

CREATE TRIGGER level2_approval_action_insert
BEFORE INSERT ON level2_approval_actions BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM approval_requests AS a
        JOIN tool_invocations AS i ON i.id = a.tool_invocation_id
        WHERE a.id = new.approval_id AND a.run_id = new.run_id
          AND i.run_id = new.run_id AND i.permission_level = 2
          AND i.tool_name = new.tool_name AND i.status = 'denied'
          AND i.error_code = 'approval_required'
    ) THEN RAISE(ABORT, 'level 2 approval proposal does not match action') END;
    SELECT CASE WHEN new.execution_invocation_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM tool_invocations AS i
        WHERE i.id = new.execution_invocation_id AND i.run_id = new.run_id
          AND i.permission_level = 2 AND i.tool_name = new.tool_name
          AND i.status = 'running'
          AND i.id != (SELECT tool_invocation_id FROM approval_requests WHERE id = new.approval_id)
    ) THEN RAISE(ABORT, 'level 2 approval execution does not match action') END;
END;

CREATE TRIGGER level2_approval_action_update
BEFORE UPDATE OF approval_id, run_id, tool_name, canonical_arguments_json,
    arguments_hash, created_at, execution_invocation_id
ON level2_approval_actions BEGIN
    SELECT CASE WHEN new.approval_id != old.approval_id
        OR new.run_id != old.run_id
        OR new.tool_name != old.tool_name
        OR new.canonical_arguments_json != old.canonical_arguments_json
        OR new.arguments_hash != old.arguments_hash
        OR new.created_at != old.created_at
        OR (old.execution_invocation_id IS NOT NULL
            AND new.execution_invocation_id IS NOT old.execution_invocation_id)
        OR (old.resolution_kind IS NOT NULL
            AND new.execution_invocation_id IS NOT old.execution_invocation_id)
    THEN RAISE(ABORT, 'level 2 approval action is immutable') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM approval_requests AS a
        JOIN tool_invocations AS i ON i.id = a.tool_invocation_id
        WHERE a.id = new.approval_id AND a.run_id = new.run_id
          AND i.run_id = new.run_id AND i.permission_level = 2
          AND i.tool_name = new.tool_name AND i.status = 'denied'
          AND i.error_code = 'approval_required'
    ) THEN RAISE(ABORT, 'level 2 approval proposal does not match action') END;
    SELECT CASE WHEN new.execution_invocation_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM tool_invocations AS i
        WHERE i.id = new.execution_invocation_id AND i.run_id = new.run_id
          AND i.permission_level = 2 AND i.tool_name = new.tool_name
          AND i.status = 'running'
          AND i.id != (SELECT tool_invocation_id FROM approval_requests WHERE id = new.approval_id)
    ) THEN RAISE(ABORT, 'level 2 approval execution does not match action') END;
END;

CREATE TRIGGER level2_approval_resolution_immutable
BEFORE UPDATE OF resolution_kind, resolution_idempotency_key
ON level2_approval_actions
WHEN old.resolution_kind IS NOT NULL OR old.resolution_idempotency_key IS NOT NULL
BEGIN
    SELECT CASE WHEN new.resolution_kind IS NOT old.resolution_kind
        OR new.resolution_idempotency_key IS NOT old.resolution_idempotency_key
    THEN RAISE(ABORT, 'level 2 approval resolution is immutable') END;
END;
