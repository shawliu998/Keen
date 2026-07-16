CREATE TABLE mastery_evidence (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES assessment_attempts(id) ON DELETE SET NULL,
    session_id TEXT REFERENCES study_sessions(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL CHECK (
        evidence_type IN (
            'diagnostic', 'quiz', 'active_recall', 'checkpoint',
            'review', 'practice', 'user_report', 'content_read', 'manual'
        )
    ),
    correctness REAL NOT NULL CHECK (correctness BETWEEN 0 AND 1),
    independence REAL NOT NULL CHECK (independence BETWEEN 0 AND 1),
    hint_level INTEGER NOT NULL DEFAULT 0 CHECK (hint_level BETWEEN 0 AND 4),
    confidence_calibration REAL CHECK (confidence_calibration BETWEEN 0 AND 1),
    weight REAL NOT NULL CHECK (weight BETWEEN 0 AND 1),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) > 0),
    created_at TEXT NOT NULL
);

CREATE INDEX mastery_evidence_concept_created_idx
ON mastery_evidence(concept_id, created_at, id);

CREATE INDEX mastery_evidence_attempt_idx
ON mastery_evidence(attempt_id)
WHERE attempt_id IS NOT NULL;

CREATE TRIGGER mastery_evidence_relationships_insert
BEFORE INSERT ON mastery_evidence BEGIN
    SELECT CASE WHEN new.session_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_sessions s
        JOIN concepts c ON c.course_id = s.course_id
        WHERE s.id = new.session_id AND c.id = new.concept_id
    ) THEN RAISE(ABORT, 'mastery evidence concept does not belong to session course') END;
    SELECT CASE WHEN new.attempt_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM assessment_attempts a
        JOIN assessment_items i ON i.id = a.item_id
        WHERE a.id = new.attempt_id
          AND (i.concept_id IS NULL OR i.concept_id = new.concept_id)
          AND (
              new.session_id IS NULL OR a.session_id IS NULL
              OR a.session_id = new.session_id
          )
    ) THEN RAISE(ABORT, 'mastery evidence attempt does not match concept or session') END;
END;

CREATE TRIGGER mastery_evidence_relationships_update
BEFORE UPDATE OF concept_id, attempt_id, session_id ON mastery_evidence BEGIN
    SELECT CASE WHEN new.session_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM study_sessions s
        JOIN concepts c ON c.course_id = s.course_id
        WHERE s.id = new.session_id AND c.id = new.concept_id
    ) THEN RAISE(ABORT, 'mastery evidence concept does not belong to session course') END;
    SELECT CASE WHEN new.attempt_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM assessment_attempts a
        JOIN assessment_items i ON i.id = a.item_id
        WHERE a.id = new.attempt_id
          AND (i.concept_id IS NULL OR i.concept_id = new.concept_id)
          AND (
              new.session_id IS NULL OR a.session_id IS NULL
              OR a.session_id = new.session_id
          )
    ) THEN RAISE(ABORT, 'mastery evidence attempt does not match concept or session') END;
END;

ALTER TABLE mastery_events
ADD COLUMN algorithm TEXT NOT NULL DEFAULT 'legacy_bkt'
CHECK (length(algorithm) > 0);

ALTER TABLE mastery_events
ADD COLUMN algorithm_version TEXT NOT NULL DEFAULT '1'
CHECK (length(algorithm_version) > 0);

ALTER TABLE mastery_events
ADD COLUMN evidence_ids_json TEXT NOT NULL DEFAULT '[]'
CHECK (json_valid(evidence_ids_json) AND json_type(evidence_ids_json) = 'array');

ALTER TABLE mastery_events
ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX mastery_events_idempotency_idx
ON mastery_events(idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE TABLE mastery_event_evidence (
    event_id INTEGER NOT NULL REFERENCES mastery_events(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL UNIQUE
        REFERENCES mastery_evidence(id) ON DELETE RESTRICT,
    PRIMARY KEY (event_id, evidence_id)
);

CREATE INDEX mastery_event_evidence_event_idx
ON mastery_event_evidence(event_id, evidence_id);
