ALTER TABLE study_tasks
ADD COLUMN source_type TEXT NOT NULL DEFAULT 'manual'
CHECK (
    source_type IN (
        'review', 'weak_concept', 'study_session', 'deadline',
        'manual', 'agent_recommendation'
    )
);

ALTER TABLE study_tasks
ADD COLUMN source_id TEXT;

ALTER TABLE study_tasks
ADD COLUMN priority_score REAL NOT NULL DEFAULT 0;

ALTER TABLE study_tasks
ADD COLUMN priority_components_json TEXT NOT NULL DEFAULT '{}'
CHECK (
    json_valid(priority_components_json)
    AND json_type(priority_components_json) = 'object'
);

ALTER TABLE study_tasks
ADD COLUMN recommended_reason TEXT NOT NULL DEFAULT '';

ALTER TABLE study_tasks
ADD COLUMN scheduled_for TEXT;

ALTER TABLE study_tasks
ADD COLUMN completed_at TEXT;

ALTER TABLE study_tasks
ADD COLUMN snoozed_until TEXT;

ALTER TABLE study_tasks
ADD COLUMN idempotency_key TEXT;

ALTER TABLE study_tasks
ADD COLUMN creation_payload_json TEXT
CHECK (
    creation_payload_json IS NULL OR (
        json_valid(creation_payload_json)
        AND json_type(creation_payload_json) = 'object'
    )
);

ALTER TABLE study_tasks
ADD COLUMN revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0);

UPDATE study_tasks
SET completed_at = updated_at
WHERE status = 'completed' AND completed_at IS NULL;

CREATE UNIQUE INDEX study_tasks_idempotency_idx
ON study_tasks(idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX study_tasks_feed_idx
ON study_tasks(status, priority_score DESC, due_at, id);

CREATE INDEX study_tasks_source_idx
ON study_tasks(source_type, source_id)
WHERE source_id IS NOT NULL;

CREATE TABLE study_task_feedback (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES study_tasks(id) ON DELETE CASCADE,
    feedback_type TEXT NOT NULL CHECK (
        feedback_type IN (
            'too_easy', 'too_hard', 'not_relevant', 'completed',
            'snoozed', 'rescheduled'
        )
    ),
    details_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(details_json) AND json_type(details_json) = 'object'),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) > 0),
    created_at TEXT NOT NULL
);

CREATE INDEX study_task_feedback_task_idx
ON study_task_feedback(task_id, created_at DESC, id);
