-- Persist the two independently idempotent parts of the first diagnostic
-- without treating a learner reflection as a scored answer.
ALTER TABLE study_checkpoints
ADD COLUMN diagnostic_begin_idempotency_key TEXT;

ALTER TABLE study_checkpoints
ADD COLUMN diagnostic_begin_payload_fingerprint TEXT;

ALTER TABLE study_checkpoints
ADD COLUMN diagnostic_answer_idempotency_key TEXT;

ALTER TABLE study_checkpoints
ADD COLUMN diagnostic_answer_payload_fingerprint TEXT;

ALTER TABLE study_checkpoints
ADD COLUMN mastery_evidence_id TEXT REFERENCES mastery_evidence(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX study_checkpoints_diagnostic_begin_idempotency_idx
ON study_checkpoints(diagnostic_begin_idempotency_key)
WHERE diagnostic_begin_idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX study_checkpoints_diagnostic_answer_idempotency_idx
ON study_checkpoints(diagnostic_answer_idempotency_key)
WHERE diagnostic_answer_idempotency_key IS NOT NULL;

CREATE TRIGGER study_checkpoints_diagnostic_begin_valid_insert
BEFORE INSERT ON study_checkpoints
WHEN new.diagnostic_begin_idempotency_key IS NOT NULL BEGIN
    SELECT CASE WHEN new.kind != 'diagnostic'
                      OR new.status != 'pending'
                      OR new.unit_id IS NULL
                      OR new.diagnostic_begin_payload_fingerprint IS NULL
                      OR length(new.diagnostic_begin_idempotency_key) NOT BETWEEN 16 AND 128
                      OR new.diagnostic_begin_idempotency_key GLOB '*[^A-Za-z0-9._:-]*'
                      OR length(new.diagnostic_begin_payload_fingerprint) != 64
                      OR new.diagnostic_begin_payload_fingerprint GLOB '*[^0-9a-f]*'
                      OR length(trim(new.prompt)) NOT BETWEEN 1 AND 6000
                      OR new.response IS NOT NULL
                      OR new.answered_at IS NOT NULL
                      OR new.diagnostic_answer_idempotency_key IS NOT NULL
                      OR new.diagnostic_answer_payload_fingerprint IS NOT NULL
                      OR new.mastery_evidence_id IS NOT NULL
        THEN RAISE(ABORT, 'diagnostic begin checkpoint is invalid') END;
END;

-- A begin record is born pending, but its one allowed lifecycle transition is
-- pending -> answered.  Validate the begin identity on that update too: an
-- answered row must never be able to bypass the original key/fingerprint
-- checks by changing only its status.
CREATE TRIGGER study_checkpoints_diagnostic_begin_valid_update
BEFORE UPDATE OF kind, status, unit_id, prompt, response, answered_at,
                 diagnostic_begin_idempotency_key,
                 diagnostic_begin_payload_fingerprint,
                 diagnostic_answer_idempotency_key,
                 diagnostic_answer_payload_fingerprint, mastery_evidence_id
ON study_checkpoints
WHEN new.diagnostic_begin_idempotency_key IS NOT NULL BEGIN
    SELECT CASE WHEN new.kind != 'diagnostic'
                      OR new.status NOT IN ('pending', 'answered')
                      OR new.unit_id IS NULL
                      OR new.diagnostic_begin_payload_fingerprint IS NULL
                      OR length(new.diagnostic_begin_idempotency_key) NOT BETWEEN 16 AND 128
                      OR new.diagnostic_begin_idempotency_key GLOB '*[^A-Za-z0-9._:-]*'
                      OR length(new.diagnostic_begin_payload_fingerprint) != 64
                      OR new.diagnostic_begin_payload_fingerprint GLOB '*[^0-9a-f]*'
                      OR length(trim(new.prompt)) NOT BETWEEN 1 AND 6000
                      OR (
                          new.status = 'pending'
                          AND (
                              new.response IS NOT NULL
                              OR new.answered_at IS NOT NULL
                              OR new.diagnostic_answer_idempotency_key IS NOT NULL
                              OR new.diagnostic_answer_payload_fingerprint IS NOT NULL
                              OR new.mastery_evidence_id IS NOT NULL
                          )
                      )
        THEN RAISE(ABORT, 'diagnostic begin checkpoint is invalid') END;
END;

-- New diagnostic writes are all-or-nothing. Existing rows remain readable so
-- an upgrade never rewrites learner data; only future diagnostic mutations are
-- constrained by these triggers.
CREATE TRIGGER study_checkpoints_diagnostic_completeness_insert
BEFORE INSERT ON study_checkpoints
WHEN new.kind = 'diagnostic' AND new.status = 'answered' BEGIN
    SELECT CASE WHEN new.diagnostic_begin_idempotency_key IS NULL
                      OR new.diagnostic_begin_payload_fingerprint IS NULL
                      OR new.diagnostic_answer_idempotency_key IS NULL
                      OR new.diagnostic_answer_payload_fingerprint IS NULL
                      OR new.mastery_evidence_id IS NULL
                      OR new.response IS NULL
                      OR new.answered_at IS NULL
                      OR length(trim(new.response)) NOT BETWEEN 1 AND 8000
                      OR length(new.diagnostic_answer_idempotency_key) NOT BETWEEN 16 AND 128
                      OR new.diagnostic_answer_idempotency_key GLOB '*[^A-Za-z0-9._:-]*'
                      OR new.diagnostic_answer_payload_fingerprint IS NULL
                      OR length(new.diagnostic_answer_payload_fingerprint) != 64
                      OR new.diagnostic_answer_payload_fingerprint GLOB '*[^0-9a-f]*'
        THEN RAISE(ABORT, 'answered diagnostic checkpoint must be complete') END;
END;

CREATE TRIGGER study_checkpoints_diagnostic_completeness_update
BEFORE UPDATE OF status, kind, answered_at, response, diagnostic_begin_idempotency_key,
                 diagnostic_begin_payload_fingerprint,
                 diagnostic_answer_idempotency_key,
                 diagnostic_answer_payload_fingerprint, mastery_evidence_id
ON study_checkpoints
WHEN new.kind = 'diagnostic' AND new.status = 'answered' BEGIN
    SELECT CASE WHEN new.diagnostic_begin_idempotency_key IS NULL
                      OR new.diagnostic_begin_payload_fingerprint IS NULL
                      OR new.diagnostic_answer_idempotency_key IS NULL
                      OR new.diagnostic_answer_payload_fingerprint IS NULL
                      OR new.mastery_evidence_id IS NULL
                      OR new.response IS NULL
                      OR new.answered_at IS NULL
                      OR length(trim(new.response)) NOT BETWEEN 1 AND 8000
                      OR length(new.diagnostic_answer_idempotency_key) NOT BETWEEN 16 AND 128
                      OR new.diagnostic_answer_idempotency_key GLOB '*[^A-Za-z0-9._:-]*'
                      OR new.diagnostic_answer_payload_fingerprint IS NULL
                      OR length(new.diagnostic_answer_payload_fingerprint) != 64
                      OR new.diagnostic_answer_payload_fingerprint GLOB '*[^0-9a-f]*'
        THEN RAISE(ABORT, 'answered diagnostic checkpoint must be complete') END;
END;

CREATE TRIGGER study_checkpoints_diagnostic_relationships_insert
BEFORE INSERT ON study_checkpoints
WHEN new.mastery_evidence_id IS NOT NULL BEGIN
    SELECT CASE WHEN new.kind != 'diagnostic' OR new.status != 'answered'
        THEN RAISE(ABORT, 'diagnostic evidence requires an answered diagnostic checkpoint') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM mastery_evidence e
        JOIN study_units u ON u.id = new.unit_id
        WHERE e.id = new.mastery_evidence_id
          AND e.session_id = new.session_id
          AND e.concept_id = u.concept_id
          AND e.evidence_type = 'user_report'
          AND e.weight = 0
    ) THEN RAISE(ABORT, 'diagnostic evidence does not match checkpoint') END;
END;

CREATE TRIGGER study_checkpoints_diagnostic_relationships_update
BEFORE UPDATE OF mastery_evidence_id, status, session_id, unit_id ON study_checkpoints
WHEN new.mastery_evidence_id IS NOT NULL BEGIN
    SELECT CASE WHEN new.kind != 'diagnostic' OR new.status != 'answered'
        THEN RAISE(ABORT, 'diagnostic evidence requires an answered diagnostic checkpoint') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM mastery_evidence e
        JOIN study_units u ON u.id = new.unit_id
        WHERE e.id = new.mastery_evidence_id
          AND e.session_id = new.session_id
          AND e.concept_id = u.concept_id
          AND e.evidence_type = 'user_report'
          AND e.weight = 0
    ) THEN RAISE(ABORT, 'diagnostic evidence does not match checkpoint') END;
END;

CREATE TRIGGER study_checkpoints_diagnostic_answer_immutable
BEFORE UPDATE OF status, kind, answered_at, response, diagnostic_answer_idempotency_key,
                 diagnostic_answer_payload_fingerprint, mastery_evidence_id
ON study_checkpoints
WHEN old.diagnostic_answer_idempotency_key IS NOT NULL BEGIN
    SELECT RAISE(ABORT, 'answered diagnostic checkpoint is immutable');
END;

CREATE TRIGGER study_checkpoints_diagnostic_begin_immutable
BEFORE UPDATE OF kind, status, diagnostic_begin_idempotency_key,
                 diagnostic_begin_payload_fingerprint,
                 session_id, unit_id, prompt, created_at
ON study_checkpoints
WHEN old.diagnostic_begin_idempotency_key IS NOT NULL
     AND NOT (
         old.kind = 'diagnostic' AND new.kind = 'diagnostic'
         AND (
             (old.status = 'pending' AND new.status IN ('pending', 'answered'))
             OR (old.status = 'answered' AND new.status = 'answered')
         )
         AND old.diagnostic_begin_idempotency_key = new.diagnostic_begin_idempotency_key
         AND old.diagnostic_begin_payload_fingerprint = new.diagnostic_begin_payload_fingerprint
         AND old.session_id = new.session_id
         AND old.unit_id = new.unit_id
         AND old.prompt = new.prompt
         AND old.created_at = new.created_at
     ) BEGIN
    SELECT RAISE(ABORT, 'diagnostic checkpoint identity is immutable');
END;

CREATE TRIGGER mastery_evidence_diagnostic_checkpoint_immutable
BEFORE UPDATE ON mastery_evidence
WHEN EXISTS (
    SELECT 1 FROM study_checkpoints c WHERE c.mastery_evidence_id = old.id
) BEGIN
    SELECT RAISE(ABORT, 'diagnostic mastery evidence is immutable');
END;

-- The evidence relationship is also defined by the checkpoint unit's primary
-- concept and its bounded concept set. Freeze those reverse edges once an
-- answered diagnostic cites the unit, otherwise an unrelated unit edit could
-- silently make immutable evidence mean something different.
CREATE TRIGGER study_units_answered_diagnostic_concepts_immutable
BEFORE UPDATE OF concept_id, concept_ids_json ON study_units
WHEN (
    new.concept_id IS NOT old.concept_id
    OR new.concept_ids_json != old.concept_ids_json
) AND EXISTS (
    SELECT 1
    FROM study_checkpoints c
    WHERE c.unit_id = old.id
      AND c.kind = 'diagnostic'
      AND c.status = 'answered'
      AND c.mastery_evidence_id IS NOT NULL
) BEGIN
    SELECT RAISE(ABORT, 'answered diagnostic unit concepts are immutable');
END;

CREATE TRIGGER study_units_plan_reparent_immutable
BEFORE UPDATE OF plan_version_id ON study_units
WHEN new.plan_version_id != old.plan_version_id BEGIN
    SELECT RAISE(ABORT, 'study units cannot be moved between plans');
END;

CREATE TRIGGER study_plan_session_reparent_immutable
BEFORE UPDATE OF session_id ON study_plan_versions
WHEN new.session_id != old.session_id BEGIN
    SELECT RAISE(ABORT, 'study plans cannot be moved between sessions');
END;

-- The session pointer is only meaningful when it points to the one active
-- unit. These triggers apply on writes only, leaving legacy data recoverable.
CREATE TRIGGER study_sessions_current_unit_active_update
BEFORE UPDATE OF current_unit_id ON study_sessions
WHEN new.current_unit_id IS NOT NULL
     AND new.current_unit_id IS NOT old.current_unit_id BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_units u
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        WHERE u.id = new.current_unit_id
          AND p.session_id = new.id
          AND u.status = 'active'
    ) THEN RAISE(ABORT, 'current unit must be active') END;
END;

CREATE TRIGGER study_units_one_active_per_session
BEFORE INSERT ON study_units
WHEN new.status = 'active' BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM study_units other
        JOIN study_plan_versions other_plan ON other_plan.id = other.plan_version_id
        JOIN study_plan_versions new_plan ON new_plan.id = new.plan_version_id
        WHERE other_plan.session_id = new_plan.session_id
          AND other.status = 'active'
    ) THEN RAISE(ABORT, 'study session already has an active unit') END;
END;

CREATE TRIGGER study_units_one_active_per_session_update
BEFORE UPDATE OF status ON study_units
WHEN new.status = 'active' BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM study_units other
        JOIN study_plan_versions other_plan ON other_plan.id = other.plan_version_id
        JOIN study_plan_versions new_plan ON new_plan.id = new.plan_version_id
        WHERE other_plan.session_id = new_plan.session_id
          AND other.id <> new.id
          AND other.status = 'active'
    ) THEN RAISE(ABORT, 'study session already has an active unit') END;
END;

CREATE TRIGGER study_units_current_unit_cannot_be_deactivated
BEFORE UPDATE OF status ON study_units
WHEN new.status <> 'active' AND EXISTS (
    SELECT 1 FROM study_sessions s WHERE s.current_unit_id = old.id
) BEGIN
    SELECT RAISE(ABORT, 'current unit must remain active');
END;
