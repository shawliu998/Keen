-- Bind both client-provided focused-study identities before source retrieval.
-- A blocked row is implementation metadata only: it creates no learning task,
-- concept, mastery, session, plan, review, or assessment state.
CREATE TABLE focused_study_request_identities (
    client_request_id TEXT PRIMARY KEY CHECK (
        length(client_request_id) BETWEEN 16 AND 128
        AND client_request_id NOT GLOB '*[^A-Za-z0-9._:-]*'
    ),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (
        length(idempotency_key) BETWEEN 16 AND 128
        AND idempotency_key NOT GLOB '*[^A-Za-z0-9._:-]*'
    ),
    payload_fingerprint TEXT NOT NULL CHECK (
        length(payload_fingerprint) = 64
        AND payload_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    course_id TEXT NOT NULL CHECK (length(course_id) BETWEEN 1 AND 128),
    goal TEXT NOT NULL CHECK (length(goal) BETWEEN 1 AND 1000),
    outcome TEXT NOT NULL CHECK (outcome IN ('blocked', 'session_created')),
    task_id TEXT REFERENCES study_tasks(id) ON DELETE RESTRICT,
    session_id TEXT REFERENCES study_sessions(id) ON DELETE RESTRICT,
    plan_id TEXT REFERENCES study_plan_versions(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (outcome = 'blocked' AND task_id IS NULL AND session_id IS NULL AND plan_id IS NULL)
        OR
        (outcome = 'session_created' AND task_id IS NOT NULL
         AND session_id IS NOT NULL AND plan_id IS NOT NULL)
    )
);

CREATE INDEX focused_study_request_outcome_idx
ON focused_study_request_identities(outcome, updated_at, client_request_id);
