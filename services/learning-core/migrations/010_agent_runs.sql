CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('conversation', 'deep_learn', 'assessment', 'review')),
    user_intent TEXT NOT NULL CHECK (length(user_intent) BETWEEN 1 AND 5000),
    mode TEXT NOT NULL CHECK (mode IN ('ask', 'teach', 'study', 'review', 'plan')),
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'waiting_approval', 'completed', 'failed', 'cancelled', 'interrupted')
    ),
    provider TEXT NOT NULL CHECK (length(provider) BETWEEN 1 AND 128),
    model TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 256),
    prompt_version TEXT NOT NULL CHECK (length(prompt_version) BETWEEN 1 AND 128),
    input_json TEXT NOT NULL CHECK (json_valid(input_json) AND json_type(input_json) = 'object'),
    error_code TEXT,
    error_detail TEXT,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 256),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE (kind, idempotency_key),
    CHECK (status != 'running' OR started_at IS NOT NULL),
    CHECK (status NOT IN ('completed', 'failed', 'cancelled', 'interrupted') OR finished_at IS NOT NULL)
);

CREATE TABLE agent_steps (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    kind TEXT NOT NULL CHECK (kind IN ('model', 'tool', 'checkpoint', 'approval')),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'interrupted')
    ),
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 500),
    input_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(input_json) AND json_type(input_json) = 'object'),
    output_json TEXT CHECK (output_json IS NULL OR json_valid(output_json)),
    error_code TEXT,
    error_detail TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE (run_id, ordinal)
);

CREATE TABLE agent_events (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    event_type TEXT NOT NULL CHECK (
        event_type IN ('metadata', 'status', 'tool_start', 'tool_result', 'content_delta', 'checkpoint', 'state_mutation', 'warning', 'done', 'error')
    ),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence)
);

CREATE TABLE tool_invocations (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_id TEXT REFERENCES agent_steps(id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 256),
    permission_level INTEGER NOT NULL CHECK (permission_level BETWEEN 1 AND 3),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled', 'denied')
    ),
    arguments_json TEXT NOT NULL
        CHECK (json_valid(arguments_json) AND json_type(arguments_json) = 'object'),
    arguments_hash TEXT NOT NULL CHECK (length(arguments_hash) = 64),
    result_summary_json TEXT CHECK (
        result_summary_json IS NULL
        OR (json_valid(result_summary_json) AND json_type(result_summary_json) = 'object')
    ),
    error_code TEXT,
    error_detail TEXT,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 256),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE (run_id, idempotency_key)
);

CREATE TABLE state_mutations (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    tool_invocation_id TEXT NOT NULL REFERENCES tool_invocations(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    entity_type TEXT NOT NULL CHECK (length(entity_type) BETWEEN 1 AND 128),
    entity_id TEXT NOT NULL CHECK (length(entity_id) BETWEEN 1 AND 256),
    operation TEXT NOT NULL CHECK (operation IN ('create', 'update', 'delete')),
    before_json TEXT CHECK (before_json IS NULL OR json_valid(before_json)),
    after_json TEXT CHECK (after_json IS NULL OR json_valid(after_json)),
    undo_json TEXT CHECK (undo_json IS NULL OR json_valid(undo_json)),
    reversible INTEGER NOT NULL CHECK (reversible IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE (tool_invocation_id, ordinal),
    CHECK (before_json IS NOT NULL OR after_json IS NOT NULL)
);

CREATE TABLE approval_requests (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    tool_invocation_id TEXT NOT NULL UNIQUE
        REFERENCES tool_invocations(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'expired', 'cancelled')),
    summary TEXT NOT NULL CHECK (length(summary) BETWEEN 1 AND 2000),
    requested_at TEXT NOT NULL,
    resolved_at TEXT,
    CHECK ((status = 'pending') = (resolved_at IS NULL))
);

CREATE INDEX agent_runs_status_updated_idx ON agent_runs(status, updated_at, id);
CREATE INDEX agent_runs_conversation_idx ON agent_runs(conversation_id, created_at, id);
CREATE INDEX agent_steps_run_idx ON agent_steps(run_id, ordinal);
CREATE INDEX agent_events_run_sequence_idx ON agent_events(run_id, sequence);
CREATE INDEX tool_invocations_run_idx ON tool_invocations(run_id, created_at, id);
CREATE INDEX state_mutations_entity_idx ON state_mutations(entity_type, entity_id, created_at);
CREATE INDEX approval_requests_pending_idx ON approval_requests(status, requested_at, id);

CREATE TRIGGER tool_invocations_step_run_insert
BEFORE INSERT ON tool_invocations WHEN new.step_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM agent_steps WHERE id = new.step_id AND run_id = new.run_id
    ) THEN RAISE(ABORT, 'tool step does not belong to run') END;
END;

CREATE TRIGGER tool_invocations_step_run_update
BEFORE UPDATE OF step_id, run_id ON tool_invocations WHEN new.step_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM agent_steps WHERE id = new.step_id AND run_id = new.run_id
    ) THEN RAISE(ABORT, 'tool step does not belong to run') END;
END;

CREATE TRIGGER state_mutations_invocation_run_insert
BEFORE INSERT ON state_mutations BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND run_id = new.run_id
    ) THEN RAISE(ABORT, 'mutation invocation does not belong to run') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND permission_level = 1
    ) THEN RAISE(ABORT, 'level 1 tools cannot mutate state') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND permission_level = 2
    ) AND (new.reversible != 1 OR new.undo_json IS NULL)
        THEN RAISE(ABORT, 'level 2 mutations must be reversible') END;
    SELECT CASE WHEN new.reversible = 1 AND new.undo_json IS NULL
        THEN RAISE(ABORT, 'reversible mutation requires undo data') END;
END;

CREATE TRIGGER state_mutations_invocation_run_update
BEFORE UPDATE OF tool_invocation_id, run_id, reversible, undo_json ON state_mutations BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND run_id = new.run_id
    ) THEN RAISE(ABORT, 'mutation invocation does not belong to run') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND permission_level = 1
    ) THEN RAISE(ABORT, 'level 1 tools cannot mutate state') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND permission_level = 2
    ) AND (new.reversible != 1 OR new.undo_json IS NULL)
        THEN RAISE(ABORT, 'level 2 mutations must be reversible') END;
    SELECT CASE WHEN new.reversible = 1 AND new.undo_json IS NULL
        THEN RAISE(ABORT, 'reversible mutation requires undo data') END;
END;

CREATE TRIGGER approval_requests_invocation_run_insert
BEFORE INSERT ON approval_requests BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND run_id = new.run_id
    ) THEN RAISE(ABORT, 'approval invocation does not belong to run') END;
END;

CREATE TRIGGER approval_requests_invocation_run_update
BEFORE UPDATE OF tool_invocation_id, run_id ON approval_requests BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM tool_invocations
        WHERE id = new.tool_invocation_id AND run_id = new.run_id
    ) THEN RAISE(ABORT, 'approval invocation does not belong to run') END;
END;
