CREATE TABLE assessments (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    session_id TEXT REFERENCES study_sessions(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
    purpose TEXT NOT NULL CHECK (purpose IN ('diagnostic', 'checkpoint', 'practice', 'quiz', 'review')),
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'archived')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT,
    CHECK (
        (status = 'draft' AND published_at IS NULL)
        OR (status IN ('published', 'archived') AND published_at IS NOT NULL)
    )
);

CREATE TABLE assessment_items (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    concept_id TEXT REFERENCES concepts(id) ON DELETE SET NULL,
    item_type TEXT NOT NULL CHECK (
        item_type IN ('single_choice', 'multiple_choice', 'true_false', 'short_answer', 'long_answer', 'fill_blank', 'step_by_step')
    ),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('introductory', 'easy', 'medium', 'hard', 'expert')),
    prompt TEXT NOT NULL CHECK (length(prompt) BETWEEN 1 AND 20000),
    options_json TEXT CHECK (
        options_json IS NULL OR (json_valid(options_json) AND json_type(options_json) = 'array')
    ),
    answer_key_json TEXT NOT NULL CHECK (json_valid(answer_key_json)),
    rubric_json TEXT CHECK (
        rubric_json IS NULL OR (json_valid(rubric_json) AND json_type(rubric_json) = 'object')
    ),
    source_chunk_ids_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(source_chunk_ids_json) AND json_type(source_chunk_ids_json) = 'array'),
    max_score REAL NOT NULL CHECK (max_score > 0 AND max_score <= 1000000),
    created_at TEXT NOT NULL,
    UNIQUE (assessment_id, ordinal)
);

CREATE TABLE assessment_attempts (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE RESTRICT,
    item_id TEXT NOT NULL REFERENCES assessment_items(id) ON DELETE RESTRICT,
    session_id TEXT REFERENCES study_sessions(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('in_progress', 'submitted', 'graded', 'cancelled')),
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 256),
    answer_json TEXT NOT NULL CHECK (json_valid(answer_json)),
    confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    total_score REAL CHECK (total_score IS NULL OR total_score >= 0),
    max_score REAL CHECK (max_score IS NULL OR max_score > 0),
    started_at TEXT NOT NULL,
    submitted_at TEXT,
    graded_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (assessment_id, idempotency_key),
    CHECK (status NOT IN ('submitted', 'graded') OR submitted_at IS NOT NULL),
    CHECK (status != 'graded' OR (graded_at IS NOT NULL AND total_score IS NOT NULL AND max_score IS NOT NULL)),
    CHECK (total_score IS NULL OR max_score IS NULL OR total_score <= max_score)
);

CREATE TABLE answer_evaluations (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    attempt_id TEXT NOT NULL REFERENCES assessment_attempts(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES assessment_items(id) ON DELETE RESTRICT,
    answer_json TEXT NOT NULL CHECK (json_valid(answer_json)),
    raw_score REAL NOT NULL CHECK (raw_score >= 0),
    hint_penalty REAL NOT NULL DEFAULT 0 CHECK (hint_penalty >= 0),
    final_score REAL NOT NULL CHECK (final_score >= 0),
    is_correct INTEGER CHECK (is_correct IS NULL OR is_correct IN (0, 1)),
    correctness TEXT NOT NULL CHECK (correctness IN ('correct', 'incorrect', 'partial')),
    score REAL NOT NULL CHECK (score >= 0),
    independence REAL NOT NULL CHECK (independence BETWEEN 0 AND 1),
    rubric_breakdown_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(rubric_breakdown_json) AND json_type(rubric_breakdown_json) = 'object'),
    evaluation_source TEXT NOT NULL CHECK (evaluation_source IN ('deterministic', 'rubric_normalized')),
    feedback TEXT NOT NULL DEFAULT '',
    evaluator_version TEXT NOT NULL CHECK (length(evaluator_version) BETWEEN 1 AND 128),
    grader_version TEXT NOT NULL CHECK (length(grader_version) BETWEEN 1 AND 128),
    created_at TEXT NOT NULL,
    UNIQUE (attempt_id, item_id),
    CHECK (final_score <= raw_score),
    CHECK (hint_penalty >= 0)
);

CREATE TABLE hint_events (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    attempt_id TEXT NOT NULL REFERENCES assessment_attempts(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES assessment_items(id) ON DELETE RESTRICT,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 4),
    penalty REAL NOT NULL CHECK (penalty >= 0),
    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 10000),
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 256),
    created_at TEXT NOT NULL,
    UNIQUE (attempt_id, item_id, idempotency_key)
);

CREATE INDEX assessments_course_idx ON assessments(course_id, updated_at DESC, id);
CREATE INDEX assessment_items_assessment_idx ON assessment_items(assessment_id, ordinal);
CREATE INDEX assessment_attempts_status_idx ON assessment_attempts(status, updated_at, id);
CREATE INDEX answer_evaluations_attempt_idx ON answer_evaluations(attempt_id, item_id);
CREATE INDEX hint_events_attempt_item_idx ON hint_events(attempt_id, item_id, created_at, id);

CREATE TRIGGER assessments_session_course_insert
BEFORE INSERT ON assessments WHEN new.session_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_sessions
        WHERE id = new.session_id AND course_id = new.course_id
    ) THEN RAISE(ABORT, 'assessment session does not belong to course') END;
END;

CREATE TRIGGER assessments_session_course_update
BEFORE UPDATE OF session_id, course_id ON assessments WHEN new.session_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_sessions
        WHERE id = new.session_id AND course_id = new.course_id
    ) THEN RAISE(ABORT, 'assessment session does not belong to course') END;
END;

CREATE TRIGGER assessments_course_immutable_with_items
BEFORE UPDATE OF course_id ON assessments
WHEN new.course_id != old.course_id
  AND EXISTS (SELECT 1 FROM assessment_items WHERE assessment_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'assessment course is immutable after items are added');
END;

CREATE TRIGGER assessment_items_concept_course_insert
BEFORE INSERT ON assessment_items WHEN new.concept_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts c JOIN assessments a ON a.id = new.assessment_id
        WHERE c.id = new.concept_id AND c.course_id = a.course_id
    ) THEN RAISE(ABORT, 'assessment item concept does not belong to course') END;
END;

CREATE TRIGGER assessment_items_concept_course_update
BEFORE UPDATE OF concept_id, assessment_id ON assessment_items WHEN new.concept_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts c JOIN assessments a ON a.id = new.assessment_id
        WHERE c.id = new.concept_id AND c.course_id = a.course_id
    ) THEN RAISE(ABORT, 'assessment item concept does not belong to course') END;
END;

CREATE TRIGGER assessment_attempts_item_assessment_insert
BEFORE INSERT ON assessment_attempts BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assessment_items
        WHERE id = new.item_id AND assessment_id = new.assessment_id
    ) THEN RAISE(ABORT, 'attempt item does not belong to assessment') END;
    SELECT CASE WHEN new.session_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM assessments a
        WHERE a.id = new.assessment_id
          AND (a.session_id IS NULL OR a.session_id = new.session_id)
    ) THEN RAISE(ABORT, 'attempt session does not match assessment') END;
END;

CREATE TRIGGER assessment_attempts_item_assessment_update
BEFORE UPDATE OF item_id, assessment_id, session_id ON assessment_attempts BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assessment_items
        WHERE id = new.item_id AND assessment_id = new.assessment_id
    ) THEN RAISE(ABORT, 'attempt item does not belong to assessment') END;
    SELECT CASE WHEN new.session_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM assessments a
        WHERE a.id = new.assessment_id
          AND (a.session_id IS NULL OR a.session_id = new.session_id)
    ) THEN RAISE(ABORT, 'attempt session does not match assessment') END;
END;

CREATE TRIGGER answer_evaluations_attempt_item_insert
BEFORE INSERT ON answer_evaluations BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assessment_attempts
        WHERE id = new.attempt_id AND item_id = new.item_id
    ) THEN RAISE(ABORT, 'evaluation item does not match attempt') END;
END;

CREATE TRIGGER answer_evaluations_attempt_item_update
BEFORE UPDATE OF attempt_id, item_id ON answer_evaluations BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assessment_attempts
        WHERE id = new.attempt_id AND item_id = new.item_id
    ) THEN RAISE(ABORT, 'evaluation item does not match attempt') END;
END;

CREATE TRIGGER hint_events_attempt_item_insert
BEFORE INSERT ON hint_events BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assessment_attempts
        WHERE id = new.attempt_id AND item_id = new.item_id
    ) THEN RAISE(ABORT, 'hint item does not match attempt') END;
END;

CREATE TRIGGER hint_events_attempt_item_update
BEFORE UPDATE OF attempt_id, item_id ON hint_events BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assessment_attempts
        WHERE id = new.attempt_id AND item_id = new.item_id
    ) THEN RAISE(ABORT, 'hint item does not match attempt') END;
END;
