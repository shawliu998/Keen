CREATE TABLE misconceptions (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (
        status IN ('suspected', 'confirmed', 'improving', 'resolved', 'dismissed')
    ),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    confirmation_source TEXT CHECK (
        confirmation_source IS NULL
        OR confirmation_source IN ('deterministic_rule', 'user')
    ),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    resolved_at TEXT,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) > 0),
    creation_payload_json TEXT NOT NULL
        CHECK (
            json_valid(creation_payload_json)
            AND json_type(creation_payload_json) = 'object'
        ),
    CHECK (status != 'confirmed' OR confirmation_source IS NOT NULL),
    CHECK (status != 'resolved' OR resolved_at IS NOT NULL),
    UNIQUE(course_id, concept_id, label)
);

CREATE TABLE misconception_evidence (
    id TEXT PRIMARY KEY,
    misconception_id TEXT NOT NULL
        REFERENCES misconceptions(id) ON DELETE CASCADE,
    mastery_evidence_id TEXT
        REFERENCES mastery_evidence(id) ON DELETE SET NULL,
    attempt_id TEXT REFERENCES assessment_attempts(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL CHECK (
        evidence_type IN (
            'repeated_error', 'distractor_pattern', 'high_confidence_error',
            'explanation_pattern', 'user_confirmation', 'manual'
        )
    ),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    details_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(details_json) AND json_type(details_json) = 'object'),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) > 0),
    created_at TEXT NOT NULL,
    CHECK (mastery_evidence_id IS NOT NULL OR attempt_id IS NOT NULL
           OR evidence_type IN ('user_confirmation', 'manual'))
);

CREATE INDEX misconceptions_course_status_idx
ON misconceptions(course_id, status, last_seen_at DESC, id);

CREATE INDEX misconceptions_concept_idx
ON misconceptions(concept_id, status, id);

CREATE INDEX misconception_evidence_parent_idx
ON misconception_evidence(misconception_id, created_at, id);

CREATE TRIGGER misconceptions_concept_course_insert
BEFORE INSERT ON misconceptions BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts
        WHERE id = new.concept_id AND course_id = new.course_id
    ) THEN RAISE(ABORT, 'misconception concept does not belong to course') END;
END;

CREATE TRIGGER misconceptions_concept_course_update
BEFORE UPDATE OF concept_id, course_id ON misconceptions BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM concepts
        WHERE id = new.concept_id AND course_id = new.course_id
    ) THEN RAISE(ABORT, 'misconception concept does not belong to course') END;
END;

CREATE TRIGGER misconception_evidence_relationships_insert
BEFORE INSERT ON misconception_evidence BEGIN
    SELECT CASE WHEN new.mastery_evidence_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM mastery_evidence e
        JOIN misconceptions m ON m.concept_id = e.concept_id
        WHERE e.id = new.mastery_evidence_id AND m.id = new.misconception_id
    ) THEN RAISE(ABORT, 'misconception evidence does not match concept') END;
    SELECT CASE WHEN new.attempt_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM assessment_attempts a
        JOIN assessment_items i ON i.id = a.item_id
        JOIN misconceptions m ON m.concept_id = i.concept_id
        WHERE a.id = new.attempt_id AND m.id = new.misconception_id
    ) THEN RAISE(ABORT, 'misconception attempt does not match concept') END;
END;

CREATE TRIGGER misconception_evidence_relationships_update
BEFORE UPDATE OF misconception_id, mastery_evidence_id, attempt_id
ON misconception_evidence BEGIN
    SELECT CASE WHEN new.mastery_evidence_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM mastery_evidence e
        JOIN misconceptions m ON m.concept_id = e.concept_id
        WHERE e.id = new.mastery_evidence_id AND m.id = new.misconception_id
    ) THEN RAISE(ABORT, 'misconception evidence does not match concept') END;
    SELECT CASE WHEN new.attempt_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM assessment_attempts a
        JOIN assessment_items i ON i.id = a.item_id
        JOIN misconceptions m ON m.concept_id = i.concept_id
        WHERE a.id = new.attempt_id AND m.id = new.misconception_id
    ) THEN RAISE(ABORT, 'misconception attempt does not match concept') END;
END;
