CREATE TABLE study_sessions (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
    mode TEXT NOT NULL CHECK (mode IN ('teach', 'study', 'review', 'plan')),
    goal TEXT NOT NULL CHECK (length(goal) BETWEEN 1 AND 5000),
    goal_scope_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(goal_scope_json) AND json_type(goal_scope_json) = 'object'),
    preferences_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(preferences_json) AND json_type(preferences_json) = 'object'),
    difficulty_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(difficulty_json) AND json_type(difficulty_json) = 'object'),
    status TEXT NOT NULL CHECK (
        status IN ('draft', 'goal_confirmation', 'diagnosing', 'planning', 'studying', 'checkpoint', 'active_recall', 'practicing', 'summarizing', 'review_scheduling', 'paused', 'completed', 'cancelled', 'failed')
    ),
    resume_from_status TEXT CHECK (
        resume_from_status IS NULL OR resume_from_status IN ('draft', 'goal_confirmation', 'diagnosing', 'planning', 'studying', 'checkpoint', 'active_recall', 'practicing', 'summarizing', 'review_scheduling')
    ),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    progress REAL NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
    estimated_minutes INTEGER NOT NULL DEFAULT 1
        CHECK (estimated_minutes BETWEEN 1 AND 1000000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    CHECK ((status = 'paused') = (resume_from_status IS NOT NULL)),
    CHECK (status NOT IN ('completed', 'cancelled', 'failed') OR finished_at IS NOT NULL)
);

CREATE TABLE study_plan_versions (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    rationale TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (session_id, version)
);

CREATE TABLE study_units (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    plan_version_id TEXT NOT NULL REFERENCES study_plan_versions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    concept_id TEXT REFERENCES concepts(id) ON DELETE SET NULL,
    concept_ids_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(concept_ids_json) AND json_type(concept_ids_json) = 'array'),
    source_chunk_ids_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(source_chunk_ids_json) AND json_type(source_chunk_ids_json) = 'array'),
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
    objective TEXT NOT NULL CHECK (length(objective) BETWEEN 1 AND 5000),
    content TEXT NOT NULL DEFAULT '',
    estimated_minutes INTEGER NOT NULL CHECK (estimated_minutes BETWEEN 1 AND 1440),
    status TEXT NOT NULL DEFAULT 'locked'
        CHECK (status IN ('locked', 'ready', 'active', 'completed', 'skipped')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (plan_version_id, ordinal)
);

ALTER TABLE study_sessions
ADD COLUMN current_unit_id TEXT REFERENCES study_units(id) ON DELETE SET NULL;

ALTER TABLE agent_runs
ADD COLUMN study_session_id TEXT REFERENCES study_sessions(id) ON DELETE SET NULL;

CREATE TRIGGER agent_runs_learning_context_insert
BEFORE INSERT ON agent_runs
WHEN new.conversation_id IS NOT NULL AND new.study_session_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_sessions s
        JOIN conversations c ON c.id = new.conversation_id
        WHERE s.id = new.study_session_id
          AND s.conversation_id = new.conversation_id
          AND (c.course_id IS NULL OR c.course_id = s.course_id)
    ) THEN RAISE(ABORT, 'agent run learning contexts do not match') END;
END;

CREATE TRIGGER agent_runs_learning_context_update
BEFORE UPDATE OF conversation_id, study_session_id ON agent_runs
WHEN new.conversation_id IS NOT NULL AND new.study_session_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_sessions s
        JOIN conversations c ON c.id = new.conversation_id
        WHERE s.id = new.study_session_id
          AND s.conversation_id = new.conversation_id
          AND (c.course_id IS NULL OR c.course_id = s.course_id)
    ) THEN RAISE(ABORT, 'agent run learning contexts do not match') END;
END;

CREATE TRIGGER study_sessions_conversation_course_insert
BEFORE INSERT ON study_sessions WHEN new.conversation_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = new.conversation_id
          AND (c.course_id IS NULL OR c.course_id = new.course_id)
    ) THEN RAISE(ABORT, 'conversation does not belong to study-session course') END;
END;

CREATE TRIGGER study_sessions_conversation_course_update
BEFORE UPDATE OF conversation_id, course_id ON study_sessions
WHEN new.conversation_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = new.conversation_id
          AND (c.course_id IS NULL OR c.course_id = new.course_id)
    ) THEN RAISE(ABORT, 'conversation does not belong to study-session course') END;
END;

CREATE TRIGGER study_units_concept_course_insert
BEFORE INSERT ON study_units WHEN new.concept_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts c
        JOIN study_plan_versions p ON p.id = new.plan_version_id
        JOIN study_sessions s ON s.id = p.session_id
        WHERE c.id = new.concept_id AND c.course_id = s.course_id
    ) THEN RAISE(ABORT, 'study-unit concept does not belong to session course') END;
END;

CREATE TRIGGER study_units_concept_course_update
BEFORE UPDATE OF concept_id, plan_version_id ON study_units
WHEN new.concept_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts c
        JOIN study_plan_versions p ON p.id = new.plan_version_id
        JOIN study_sessions s ON s.id = p.session_id
        WHERE c.id = new.concept_id AND c.course_id = s.course_id
    ) THEN RAISE(ABORT, 'study-unit concept does not belong to session course') END;
END;

CREATE TRIGGER study_sessions_current_unit_insert
BEFORE INSERT ON study_sessions WHEN new.current_unit_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_units u
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        WHERE u.id = new.current_unit_id AND p.session_id = new.id
    ) THEN RAISE(ABORT, 'current unit does not belong to session') END;
END;

CREATE TRIGGER study_sessions_current_unit_update
BEFORE UPDATE OF current_unit_id ON study_sessions WHEN new.current_unit_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_units u
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        WHERE u.id = new.current_unit_id AND p.session_id = new.id
    ) THEN RAISE(ABORT, 'current unit does not belong to session') END;
END;

CREATE TABLE study_checkpoints (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    unit_id TEXT REFERENCES study_units(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('diagnostic', 'comprehension', 'active_recall', 'practice', 'reflection')),
    prompt TEXT NOT NULL CHECK (length(prompt) BETWEEN 1 AND 20000),
    response TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'answered', 'skipped')),
    created_at TEXT NOT NULL,
    answered_at TEXT,
    CHECK ((status = 'answered') = (answered_at IS NOT NULL))
);

CREATE TRIGGER study_checkpoints_unit_session_insert
BEFORE INSERT ON study_checkpoints WHEN new.unit_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_units u
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        WHERE u.id = new.unit_id AND p.session_id = new.session_id
    ) THEN RAISE(ABORT, 'checkpoint unit does not belong to session') END;
END;

CREATE TRIGGER study_checkpoints_unit_session_update
BEFORE UPDATE OF unit_id, session_id ON study_checkpoints WHEN new.unit_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_units u
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        WHERE u.id = new.unit_id AND p.session_id = new.session_id
    ) THEN RAISE(ABORT, 'checkpoint unit does not belong to session') END;
END;

CREATE TABLE study_session_events (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    event_type TEXT NOT NULL CHECK (
        event_type IN ('created', 'status_changed', 'plan_created', 'unit_changed', 'checkpoint_created', 'checkpoint_answered', 'recovered', 'warning')
    ),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (session_id, sequence)
);

CREATE INDEX study_sessions_status_updated_idx ON study_sessions(status, updated_at, id);
CREATE INDEX study_sessions_course_idx ON study_sessions(course_id, updated_at DESC, id);
CREATE INDEX study_plan_versions_session_idx ON study_plan_versions(session_id, version DESC);
CREATE INDEX study_units_plan_idx ON study_units(plan_version_id, ordinal);
CREATE INDEX study_checkpoints_session_idx ON study_checkpoints(session_id, created_at, id);
CREATE INDEX study_session_events_session_idx ON study_session_events(session_id, sequence);
