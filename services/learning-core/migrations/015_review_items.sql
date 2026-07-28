CREATE TABLE review_items (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (
        item_type IN (
            'flashcard', 'free_recall', 'concept_explanation',
            'error_replay', 'practice_problem'
        )
    ),
    prompt TEXT NOT NULL CHECK (length(trim(prompt)) > 0),
    expected_answer_json TEXT NOT NULL
        CHECK (json_valid(expected_answer_json)),
    source_type TEXT NOT NULL CHECK (
        source_type IN (
            'mastery_evidence', 'misconception', 'assessment',
            'study_session', 'manual', 'agent_recommendation'
        )
    ),
    source_id TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'archived')),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) > 0),
    creation_payload_json TEXT NOT NULL
        CHECK (
            json_valid(creation_payload_json)
            AND json_type(creation_payload_json) = 'object'
        ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE review_schedules (
    review_item_id TEXT PRIMARY KEY
        REFERENCES review_items(id) ON DELETE CASCADE,
    difficulty REAL NOT NULL CHECK (difficulty BETWEEN 1 AND 10),
    stability REAL NOT NULL CHECK (stability >= 0),
    due_at TEXT NOT NULL,
    last_reviewed_at TEXT,
    repetitions INTEGER NOT NULL DEFAULT 0 CHECK (repetitions >= 0),
    lapses INTEGER NOT NULL DEFAULT 0 CHECK (lapses >= 0),
    state TEXT NOT NULL CHECK (
        state IN ('new', 'learning', 'review', 'relearning')
    ),
    scheduler TEXT NOT NULL DEFAULT 'fsrs' CHECK (length(scheduler) > 0),
    scheduler_version TEXT NOT NULL CHECK (length(scheduler_version) > 0),
    scheduler_state_json TEXT NOT NULL DEFAULT '{}'
        CHECK (
            json_valid(scheduler_state_json)
            AND json_type(scheduler_state_json) = 'object'
        ),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE review_attempts (
    id TEXT PRIMARY KEY,
    review_item_id TEXT NOT NULL
        REFERENCES review_items(id) ON DELETE CASCADE,
    rating TEXT NOT NULL CHECK (rating IN ('again', 'hard', 'good', 'easy')),
    response_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(response_json)),
    schedule_before_json TEXT NOT NULL
        CHECK (
            json_valid(schedule_before_json)
            AND json_type(schedule_before_json) = 'object'
        ),
    schedule_after_json TEXT NOT NULL
        CHECK (
            json_valid(schedule_after_json)
            AND json_type(schedule_after_json) = 'object'
        ),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) > 0),
    reviewed_at TEXT NOT NULL
);

CREATE INDEX review_items_course_status_idx
ON review_items(course_id, status, updated_at DESC, id);

CREATE INDEX review_items_concept_idx
ON review_items(concept_id, status, id);

CREATE INDEX review_schedules_due_idx
ON review_schedules(state, due_at, review_item_id);

CREATE INDEX review_attempts_item_reviewed_idx
ON review_attempts(review_item_id, reviewed_at DESC, id);

CREATE TRIGGER review_items_concept_course_insert
BEFORE INSERT ON review_items BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts
        WHERE id = new.concept_id AND course_id = new.course_id
    ) THEN RAISE(ABORT, 'review item concept does not belong to course') END;
END;

CREATE TRIGGER review_items_concept_course_update
BEFORE UPDATE OF concept_id, course_id ON review_items BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts
        WHERE id = new.concept_id AND course_id = new.course_id
    ) THEN RAISE(ABORT, 'review item concept does not belong to course') END;
END;
