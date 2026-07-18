-- The practice ledger deliberately follows active recall rather than being a
-- free-standing quiz.  It freezes the selected remedial exercise and its one
-- deterministic mastery application so recovery/replay cannot double count.
CREATE TABLE study_practice_runs (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE RESTRICT,
    unit_id TEXT NOT NULL REFERENCES study_units(id) ON DELETE RESTRICT,
    predecessor_active_recall_run_id TEXT NOT NULL UNIQUE
        REFERENCES study_active_recall_runs(id) ON DELETE RESTRICT,
    checkpoint_id TEXT NOT NULL UNIQUE REFERENCES study_checkpoints(id) ON DELETE RESTRICT,
    assessment_id TEXT NOT NULL UNIQUE REFERENCES assessments(id) ON DELETE RESTRICT,
    item_id TEXT NOT NULL UNIQUE REFERENCES assessment_items(id) ON DELETE RESTRICT,
    concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE RESTRICT,
    mastery_attempts_before INTEGER NOT NULL CHECK (mastery_attempts_before >= 0),
    source_chunk_ids_json TEXT NOT NULL CHECK (
        json_valid(source_chunk_ids_json) AND json_type(source_chunk_ids_json) = 'array'
        AND json_array_length(source_chunk_ids_json) BETWEEN 1 AND 8
    ),
    source_content_fingerprint TEXT NOT NULL CHECK (
        length(source_content_fingerprint) = 64
        AND source_content_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    accepted_answers_fingerprint TEXT NOT NULL CHECK (
        length(accepted_answers_fingerprint) = 64
        AND accepted_answers_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    generator_version TEXT NOT NULL CHECK (length(generator_version) BETWEEN 1 AND 128),
    status TEXT NOT NULL CHECK (status IN ('pending', 'answered', 'cancelled')),
    begin_idempotency_key TEXT NOT NULL UNIQUE CHECK (
        length(begin_idempotency_key) BETWEEN 16 AND 128
        AND begin_idempotency_key NOT GLOB '*[^A-Za-z0-9._:-]*'
    ),
    begin_payload_fingerprint TEXT NOT NULL CHECK (
        length(begin_payload_fingerprint) = 64
        AND begin_payload_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    answer_idempotency_key TEXT UNIQUE CHECK (
        answer_idempotency_key IS NULL OR (
            length(answer_idempotency_key) BETWEEN 16 AND 128
            AND answer_idempotency_key NOT GLOB '*[^A-Za-z0-9._:-]*'
        )
    ),
    answer_payload_fingerprint TEXT CHECK (
        answer_payload_fingerprint IS NULL OR (
            length(answer_payload_fingerprint) = 64
            AND answer_payload_fingerprint NOT GLOB '*[^0-9a-f]*'
        )
    ),
    attempt_id TEXT UNIQUE REFERENCES assessment_attempts(id) ON DELETE RESTRICT,
    evaluation_id TEXT UNIQUE REFERENCES answer_evaluations(id) ON DELETE RESTRICT,
    mastery_evidence_id TEXT UNIQUE REFERENCES mastery_evidence(id) ON DELETE RESTRICT,
    mastery_event_id INTEGER UNIQUE REFERENCES mastery_events(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    answered_at TEXT,
    cancelled_at TEXT,
    cancellation_reason TEXT CHECK (cancellation_reason IS NULL OR cancellation_reason IN ('session_cancelled', 'session_failed')),
    CHECK (
        (status = 'pending' AND answer_idempotency_key IS NULL AND answer_payload_fingerprint IS NULL
         AND attempt_id IS NULL AND evaluation_id IS NULL AND mastery_evidence_id IS NULL
         AND mastery_event_id IS NULL AND answered_at IS NULL AND cancelled_at IS NULL
         AND cancellation_reason IS NULL)
        OR
        (status = 'answered' AND answer_idempotency_key IS NOT NULL AND answer_payload_fingerprint IS NOT NULL
         AND attempt_id IS NOT NULL AND evaluation_id IS NOT NULL AND mastery_evidence_id IS NOT NULL
         AND mastery_event_id IS NOT NULL AND answered_at IS NOT NULL AND cancelled_at IS NULL
         AND cancellation_reason IS NULL)
        OR
        (status = 'cancelled' AND answer_idempotency_key IS NULL AND answer_payload_fingerprint IS NULL
         AND attempt_id IS NULL AND evaluation_id IS NULL AND mastery_evidence_id IS NULL
         AND mastery_event_id IS NULL AND answered_at IS NULL AND cancelled_at IS NOT NULL
         AND cancellation_reason IS NOT NULL)
    )
);

CREATE INDEX study_practice_runs_session_created_idx
ON study_practice_runs(session_id, created_at, id);

CREATE TRIGGER study_practice_runs_relationships_insert
BEFORE INSERT ON study_practice_runs BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_sessions s
        JOIN study_units u ON u.id = new.unit_id
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        JOIN concepts c ON c.id = new.concept_id
        JOIN mastery m ON m.concept_id = c.id
        JOIN study_active_recall_runs ar ON ar.id = new.predecessor_active_recall_run_id
        WHERE s.id = new.session_id AND s.course_id = new.course_id
          AND s.status = 'practicing' AND s.current_unit_id = u.id AND u.status = 'active'
          AND p.session_id = s.id AND u.concept_id = c.id AND c.course_id = s.course_id
          AND EXISTS (SELECT 1 FROM json_each(u.concept_ids_json) WHERE value = c.id)
          AND m.attempts = new.mastery_attempts_before
          AND ar.status = 'answered' AND ar.course_id = new.course_id
          AND ar.session_id = new.session_id AND ar.unit_id = new.unit_id
          AND ar.concept_id = new.concept_id
    ) THEN RAISE(ABORT, 'practice run is outside the answered active recall unit') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_units WHERE id = new.unit_id
          AND source_chunk_ids_json = new.source_chunk_ids_json
    ) THEN RAISE(ABORT, 'practice sources do not match the current unit') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assessments a
        JOIN assessment_items i ON i.assessment_id = a.id
        JOIN study_checkpoints cp ON cp.id = new.checkpoint_id
        WHERE a.id = new.assessment_id AND a.course_id = new.course_id
          AND a.session_id = new.session_id AND a.status = 'published' AND a.purpose = 'practice'
          AND i.id = new.item_id AND i.ordinal = 0 AND i.item_type = 'fill_blank'
          AND i.concept_id = new.concept_id AND i.source_chunk_ids_json = new.source_chunk_ids_json
          AND cp.session_id = new.session_id AND cp.unit_id = new.unit_id
          AND cp.kind = 'practice' AND cp.status = 'pending' AND cp.prompt = i.prompt
          AND cp.response IS NULL AND cp.diagnostic_begin_idempotency_key IS NULL
          AND cp.diagnostic_answer_idempotency_key IS NULL AND cp.mastery_evidence_id IS NULL
          AND (SELECT COUNT(*) FROM assessment_items WHERE assessment_id = a.id) = 1
    ) THEN RAISE(ABORT, 'practice assessment or checkpoint is invalid') END;
END;

CREATE TRIGGER study_practice_runs_relationships_update
BEFORE UPDATE ON study_practice_runs BEGIN
    SELECT CASE WHEN old.status != 'pending' OR new.status NOT IN ('answered', 'cancelled')
        THEN RAISE(ABORT, 'practice run lifecycle is immutable') END;
    SELECT CASE WHEN new.id != old.id OR new.course_id != old.course_id
        OR new.session_id != old.session_id OR new.unit_id != old.unit_id
        OR new.predecessor_active_recall_run_id != old.predecessor_active_recall_run_id
        OR new.checkpoint_id != old.checkpoint_id OR new.assessment_id != old.assessment_id
        OR new.item_id != old.item_id OR new.concept_id != old.concept_id
        OR new.mastery_attempts_before != old.mastery_attempts_before
        OR new.source_chunk_ids_json != old.source_chunk_ids_json
        OR new.source_content_fingerprint != old.source_content_fingerprint
        OR new.accepted_answers_fingerprint != old.accepted_answers_fingerprint
        OR new.generator_version != old.generator_version
        OR new.begin_idempotency_key != old.begin_idempotency_key
        OR new.begin_payload_fingerprint != old.begin_payload_fingerprint
        OR new.created_at != old.created_at
        THEN RAISE(ABORT, 'practice run identity is immutable') END;
    SELECT CASE WHEN new.status = 'answered' AND NOT EXISTS (
        SELECT 1 FROM study_sessions s JOIN study_units u ON u.id = new.unit_id
        WHERE s.id = new.session_id AND s.course_id = new.course_id
          AND s.status = 'practicing' AND s.current_unit_id = u.id
          AND u.status = 'active' AND u.concept_id = new.concept_id
    ) THEN RAISE(ABORT, 'answered practice is outside the current unit') END;
    SELECT CASE WHEN new.status = 'answered' AND NOT EXISTS (
        SELECT 1 FROM assessment_attempts at
        JOIN assessment_items item ON item.id = at.item_id
        JOIN answer_evaluations ev ON ev.attempt_id = at.id AND ev.item_id = at.item_id
        JOIN mastery_evidence me ON me.attempt_id = at.id
        JOIN mastery_event_evidence mee ON mee.evidence_id = me.id
        JOIN mastery_events event ON event.id = mee.event_id
        JOIN study_checkpoints cp ON cp.id = new.checkpoint_id
        WHERE at.id = new.attempt_id AND at.assessment_id = new.assessment_id
          AND at.item_id = new.item_id AND at.session_id = new.session_id AND at.status = 'graded'
          AND ev.id = new.evaluation_id AND at.answer_json = ev.answer_json
          AND at.total_score = ev.final_score AND at.max_score = item.max_score
          AND ev.evaluation_source = 'deterministic' AND ev.correctness IN ('correct', 'incorrect')
          AND ev.is_correct = CASE ev.correctness WHEN 'correct' THEN 1 ELSE 0 END
          AND ev.hint_penalty = 0 AND ev.raw_score = ev.final_score AND ev.score = ev.final_score
          AND at.max_score > 0 AND ev.final_score = CASE ev.correctness WHEN 'correct' THEN at.max_score ELSE 0 END
          AND me.id = new.mastery_evidence_id AND me.session_id = new.session_id
          AND me.concept_id = new.concept_id AND me.evidence_type = 'practice'
          AND abs(me.correctness - (ev.final_score / at.max_score)) <= 0.0000005
          AND abs(me.independence - ev.independence) <= 0.0000005 AND me.weight > 0
          AND event.id = new.mastery_event_id AND event.concept_id = new.concept_id
          AND event.correct = ev.is_correct AND event.algorithm = 'weighted_bkt'
          AND event.algorithm_version = 'weighted-bkt/1.0.0' AND event.observed_at = new.answered_at
          AND event.id = (SELECT MAX(latest.id) FROM mastery_events latest WHERE latest.concept_id = new.concept_id)
          AND json_array_length(event.evidence_ids_json) = 1 AND json_extract(event.evidence_ids_json, '$[0]') = me.id
          AND EXISTS (SELECT 1 FROM mastery m WHERE m.concept_id = new.concept_id
              AND abs(m.probability - event.probability_after) <= 0.0000005
              AND m.attempts = new.mastery_attempts_before + 1 AND m.updated_at = event.observed_at)
          AND cp.status = 'answered' AND cp.response = 'Objective response recorded.' AND cp.answered_at = new.answered_at
    ) THEN RAISE(ABORT, 'practice scoring chain is invalid') END;
    SELECT CASE WHEN new.status = 'cancelled' AND NOT EXISTS (
        SELECT 1 FROM study_sessions s WHERE s.id = new.session_id AND new.cancelled_at = s.updated_at
          AND ((s.status = 'cancelled' AND new.cancellation_reason = 'session_cancelled')
            OR (s.status = 'failed' AND new.cancellation_reason = 'session_failed'))
    ) THEN RAISE(ABORT, 'practice cancellation is invalid') END;
END;

CREATE TRIGGER study_practice_runs_no_delete BEFORE DELETE ON study_practice_runs BEGIN
    SELECT RAISE(ABORT, 'practice ledger is immutable');
END;

CREATE TRIGGER assessments_practice_immutable BEFORE UPDATE ON assessments
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE assessment_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice assessment is immutable');
END;
CREATE TRIGGER assessment_items_practice_immutable BEFORE UPDATE ON assessment_items
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE item_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice item is immutable');
END;
CREATE TRIGGER assessment_items_practice_no_insert BEFORE INSERT ON assessment_items
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE assessment_id = new.assessment_id) BEGIN
    SELECT RAISE(ABORT, 'practice assessment cannot gain items');
END;
CREATE TRIGGER study_units_practice_semantics_immutable
BEFORE UPDATE OF plan_version_id, concept_id, concept_ids_json, source_chunk_ids_json, content ON study_units
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE unit_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice unit semantics are immutable');
END;
CREATE TRIGGER concepts_practice_course_immutable BEFORE UPDATE OF course_id ON concepts
WHEN new.course_id != old.course_id AND EXISTS (SELECT 1 FROM study_practice_runs WHERE concept_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice concept course is immutable');
END;

CREATE TRIGGER assessment_attempts_practice_session_insert
BEFORE INSERT ON assessment_attempts WHEN EXISTS (
    SELECT 1 FROM study_practice_runs r WHERE r.assessment_id = new.assessment_id AND r.item_id = new.item_id
) BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_practice_runs r JOIN assessments a ON a.id = r.assessment_id
        WHERE r.assessment_id = new.assessment_id AND r.item_id = new.item_id
          AND new.session_id = r.session_id AND a.session_id = r.session_id AND a.course_id = r.course_id
    ) THEN RAISE(ABORT, 'practice attempt session does not match assessment') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM assessment_attempts old JOIN study_practice_runs r
          ON r.assessment_id = old.assessment_id AND r.item_id = old.item_id AND r.session_id = old.session_id
        WHERE r.assessment_id = new.assessment_id AND r.item_id = new.item_id AND r.session_id = new.session_id
    ) THEN RAISE(ABORT, 'practice assessment already has an attempt') END;
END;
CREATE TRIGGER assessment_attempts_practice_session_update
BEFORE UPDATE OF assessment_id, item_id, session_id ON assessment_attempts WHEN EXISTS (
    SELECT 1 FROM study_practice_runs r
    WHERE (r.assessment_id = old.assessment_id AND r.item_id = old.item_id)
       OR (r.assessment_id = new.assessment_id AND r.item_id = new.item_id)
) BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_practice_runs r JOIN assessments a ON a.id = r.assessment_id
        WHERE r.assessment_id = new.assessment_id AND r.item_id = new.item_id
          AND new.session_id = r.session_id AND a.session_id = r.session_id AND a.course_id = r.course_id
    ) THEN RAISE(ABORT, 'practice attempt session does not match assessment') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM assessment_attempts old JOIN study_practice_runs r
          ON r.assessment_id = old.assessment_id AND r.item_id = old.item_id AND r.session_id = old.session_id
        WHERE old.id != new.id AND r.assessment_id = new.assessment_id
          AND r.item_id = new.item_id AND r.session_id = new.session_id
    ) THEN RAISE(ABORT, 'practice assessment already has an attempt') END;
END;
CREATE TRIGGER assessment_attempts_practice_immutable BEFORE UPDATE ON assessment_attempts
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE attempt_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice attempt is immutable');
END;
CREATE TRIGGER answer_evaluations_practice_immutable BEFORE UPDATE ON answer_evaluations
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE evaluation_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice evaluation is immutable');
END;
CREATE TRIGGER mastery_evidence_practice_immutable BEFORE UPDATE ON mastery_evidence
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE mastery_evidence_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice evidence is immutable');
END;
CREATE TRIGGER mastery_events_practice_immutable BEFORE UPDATE ON mastery_events
WHEN EXISTS (SELECT 1 FROM study_practice_runs WHERE mastery_event_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice mastery event is immutable');
END;
CREATE TRIGGER mastery_evidence_practice_attempt_once_insert
BEFORE INSERT ON mastery_evidence WHEN new.attempt_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM assessment_attempts at JOIN study_practice_runs r
      ON r.assessment_id = at.assessment_id AND r.item_id = at.item_id AND r.session_id = at.session_id
    WHERE at.id = new.attempt_id
) BEGIN
    SELECT CASE WHEN EXISTS (SELECT 1 FROM mastery_evidence WHERE attempt_id = new.attempt_id)
      THEN RAISE(ABORT, 'practice attempt already has mastery evidence') END;
END;
CREATE TRIGGER mastery_evidence_practice_attempt_once_update
BEFORE UPDATE OF attempt_id ON mastery_evidence
WHEN new.attempt_id IS NOT old.attempt_id AND EXISTS (
    SELECT 1 FROM assessment_attempts at JOIN study_practice_runs r
      ON r.assessment_id = at.assessment_id AND r.item_id = at.item_id AND r.session_id = at.session_id
    WHERE at.id IN (old.attempt_id, new.attempt_id)
) BEGIN
    SELECT CASE WHEN new.attempt_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM assessment_attempts at JOIN study_practice_runs r
          ON r.assessment_id = at.assessment_id AND r.item_id = at.item_id AND r.session_id = at.session_id
        WHERE at.id = new.attempt_id
    ) THEN RAISE(ABORT, 'practice evidence must remain attached to its attempt') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM mastery_evidence old WHERE old.attempt_id = new.attempt_id AND old.id != new.id
    ) THEN RAISE(ABORT, 'practice attempt already has mastery evidence') END;
END;

CREATE TRIGGER study_sessions_practice_course_immutable
BEFORE UPDATE OF course_id ON study_sessions
WHEN new.course_id != old.course_id
 AND EXISTS (SELECT 1 FROM study_practice_runs WHERE session_id = old.id) BEGIN
    SELECT RAISE(ABORT, 'practice session course is immutable');
END;
CREATE TRIGGER mastery_event_evidence_practice_no_mutation_insert
BEFORE INSERT ON mastery_event_evidence WHEN EXISTS (
    SELECT 1 FROM study_practice_runs r WHERE r.mastery_event_id = new.event_id OR r.mastery_evidence_id = new.evidence_id
) BEGIN SELECT RAISE(ABORT, 'practice mastery-event evidence is immutable'); END;
CREATE TRIGGER mastery_event_evidence_practice_no_mutation_update
BEFORE UPDATE ON mastery_event_evidence WHEN EXISTS (
    SELECT 1 FROM study_practice_runs r WHERE r.mastery_event_id IN (old.event_id, new.event_id)
       OR r.mastery_evidence_id IN (old.evidence_id, new.evidence_id)
) BEGIN SELECT RAISE(ABORT, 'practice mastery-event evidence is immutable'); END;
CREATE TRIGGER mastery_event_evidence_practice_no_mutation_delete
BEFORE DELETE ON mastery_event_evidence WHEN EXISTS (
    SELECT 1 FROM study_practice_runs r WHERE r.mastery_event_id = old.event_id OR r.mastery_evidence_id = old.evidence_id
) BEGIN SELECT RAISE(ABORT, 'practice mastery-event evidence is immutable'); END;

CREATE TRIGGER study_checkpoints_practice_immutable
BEFORE UPDATE ON study_checkpoints WHEN old.kind = 'practice'
 AND EXISTS (SELECT 1 FROM study_practice_runs WHERE checkpoint_id = old.id)
 AND NOT (
    (old.status = 'pending' AND new.status = 'answered' AND old.id = new.id
     AND old.session_id = new.session_id AND old.unit_id = new.unit_id AND old.kind = new.kind
     AND old.prompt = new.prompt AND old.created_at = new.created_at
     AND new.response = 'Objective response recorded.' AND new.answered_at IS NOT NULL
     AND new.diagnostic_begin_idempotency_key IS NULL AND new.diagnostic_answer_idempotency_key IS NULL
     AND new.mastery_evidence_id IS NULL)
    OR
    (old.status = 'pending' AND new.status = 'skipped' AND old.id = new.id
     AND old.session_id = new.session_id AND old.unit_id = new.unit_id AND old.kind = new.kind
     AND old.prompt = new.prompt AND old.created_at = new.created_at AND new.response IS NULL
     AND new.answered_at IS NULL AND new.diagnostic_begin_idempotency_key IS NULL
     AND new.diagnostic_answer_idempotency_key IS NULL AND new.mastery_evidence_id IS NULL
     AND EXISTS (SELECT 1 FROM study_practice_runs r JOIN study_sessions s ON s.id = r.session_id
       WHERE r.checkpoint_id = old.id AND r.status = 'cancelled' AND s.status IN ('cancelled', 'failed')))
 ) BEGIN SELECT RAISE(ABORT, 'practice checkpoint is immutable'); END;

CREATE TRIGGER study_sessions_pending_practice_transition_guard
BEFORE UPDATE OF status ON study_sessions WHEN old.status = 'practicing'
 AND new.status NOT IN ('practicing', 'paused', 'cancelled', 'failed')
 AND EXISTS (SELECT 1 FROM study_practice_runs WHERE session_id = old.id AND status = 'pending')
BEGIN SELECT RAISE(ABORT, 'pending practice cannot be skipped'); END;

CREATE TRIGGER study_sessions_terminalize_pending_practice
AFTER UPDATE OF status ON study_sessions WHEN new.status IN ('cancelled', 'failed')
 AND EXISTS (SELECT 1 FROM study_practice_runs WHERE session_id = new.id AND status = 'pending')
BEGIN
    UPDATE study_practice_runs SET status = 'cancelled', cancelled_at = new.updated_at,
      cancellation_reason = CASE new.status WHEN 'cancelled' THEN 'session_cancelled' ELSE 'session_failed' END
    WHERE session_id = new.id AND status = 'pending';
    UPDATE study_checkpoints SET status = 'skipped'
    WHERE id IN (SELECT checkpoint_id FROM study_practice_runs WHERE session_id = new.id
      AND status = 'cancelled' AND cancelled_at = new.updated_at) AND status = 'pending';
END;
