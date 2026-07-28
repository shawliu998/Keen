-- New sessions may opt into one deterministic post-recall branch. Existing
-- sessions remain on the canonical recall -> practice flow because NULL is
-- intentionally preserved during this forward-only migration.
ALTER TABLE study_sessions
ADD COLUMN adaptive_policy_version TEXT CHECK (
    adaptive_policy_version IS NULL
    OR adaptive_policy_version = 'adaptive-session-policy/1.0.0'
);

CREATE TRIGGER study_sessions_adaptive_policy_immutable
BEFORE UPDATE OF adaptive_policy_version ON study_sessions
WHEN new.adaptive_policy_version IS NOT old.adaptive_policy_version BEGIN
    SELECT RAISE(ABORT, 'study session adaptive policy is immutable');
END;

CREATE TABLE study_adaptive_actions (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE RESTRICT,
    unit_id TEXT NOT NULL REFERENCES study_units(id) ON DELETE RESTRICT,
    predecessor_active_recall_run_id TEXT NOT NULL
        REFERENCES study_active_recall_runs(id) ON DELETE RESTRICT,
    predecessor_action_id TEXT REFERENCES study_adaptive_actions(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('remediate', 'practice')),
    reason_code TEXT NOT NULL CHECK (
        reason_code IN (
            'active_recall_correct',
            'active_recall_incorrect',
            'remediation_completed'
        )
    ),
    policy_version TEXT NOT NULL CHECK (
        policy_version = 'adaptive-session-policy/1.0.0'
    ),
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'cancelled')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    completion_idempotency_key TEXT UNIQUE CHECK (
        completion_idempotency_key IS NULL OR (
            length(completion_idempotency_key) BETWEEN 16 AND 128
            AND completion_idempotency_key NOT GLOB '*[^A-Za-z0-9._:-]*'
        )
    ),
    completion_payload_fingerprint TEXT CHECK (
        completion_payload_fingerprint IS NULL OR (
            length(completion_payload_fingerprint) = 64
            AND completion_payload_fingerprint NOT GLOB '*[^0-9a-f]*'
        )
    ),
    practice_run_id TEXT UNIQUE REFERENCES study_practice_runs(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    cancelled_at TEXT,
    UNIQUE (predecessor_active_recall_run_id, kind),
    CHECK (
        (status = 'pending' AND revision = 0
         AND completion_idempotency_key IS NULL
         AND completion_payload_fingerprint IS NULL
         AND practice_run_id IS NULL AND started_at IS NULL
         AND completed_at IS NULL AND cancelled_at IS NULL)
        OR
        (status = 'completed' AND revision = 1
         AND started_at IS NOT NULL AND completed_at IS NOT NULL
         AND cancelled_at IS NULL
         AND (
             (kind = 'remediate' AND completion_idempotency_key IS NOT NULL
              AND completion_payload_fingerprint IS NOT NULL
              AND practice_run_id IS NULL)
             OR
             (kind = 'practice' AND completion_idempotency_key IS NULL
              AND completion_payload_fingerprint IS NULL
              AND practice_run_id IS NOT NULL)
         ))
        OR
        (status = 'cancelled' AND revision = 1
         AND completion_idempotency_key IS NULL
         AND completion_payload_fingerprint IS NULL
         AND practice_run_id IS NULL AND started_at IS NULL
         AND completed_at IS NULL AND cancelled_at IS NOT NULL)
    )
);

CREATE INDEX study_adaptive_actions_session_created_idx
ON study_adaptive_actions(session_id, created_at, id);

CREATE TRIGGER study_adaptive_actions_relationships_insert
BEFORE INSERT ON study_adaptive_actions BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM study_sessions s
        JOIN study_units u ON u.id = new.unit_id
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        JOIN study_active_recall_runs ar
          ON ar.id = new.predecessor_active_recall_run_id
        JOIN answer_evaluations ev ON ev.id = ar.evaluation_id
        WHERE s.id = new.session_id AND s.course_id = new.course_id
          AND s.adaptive_policy_version = new.policy_version
          AND s.status = 'practicing' AND s.current_unit_id = u.id
          AND u.status = 'active' AND p.session_id = s.id
          AND ar.course_id = new.course_id AND ar.session_id = new.session_id
          AND ar.unit_id = new.unit_id AND ar.status = 'answered'
          AND (
              (new.predecessor_action_id IS NULL
               AND new.kind = 'practice'
               AND new.reason_code = 'active_recall_correct'
               AND ev.correctness = 'correct')
              OR
              (new.predecessor_action_id IS NULL
               AND new.kind = 'remediate'
               AND new.reason_code = 'active_recall_incorrect'
               AND ev.correctness = 'incorrect')
              OR
              (new.predecessor_action_id IS NOT NULL
               AND new.kind = 'practice'
               AND new.reason_code = 'remediation_completed'
               AND ev.correctness = 'incorrect'
               AND EXISTS (
                   SELECT 1 FROM study_adaptive_actions prior
                   WHERE prior.id = new.predecessor_action_id
                     AND prior.course_id = new.course_id
                     AND prior.session_id = new.session_id
                     AND prior.unit_id = new.unit_id
                     AND prior.predecessor_active_recall_run_id = ar.id
                     AND prior.kind = 'remediate'
                     AND prior.status = 'completed'
               ))
          )
    ) THEN RAISE(ABORT, 'adaptive action is outside its answered recall branch') END;
END;

CREATE TRIGGER study_adaptive_actions_relationships_update
BEFORE UPDATE ON study_adaptive_actions BEGIN
    SELECT CASE WHEN old.status != 'pending' OR new.status NOT IN ('completed', 'cancelled')
        THEN RAISE(ABORT, 'adaptive action lifecycle is immutable') END;
    SELECT CASE WHEN new.id != old.id OR new.course_id != old.course_id
        OR new.session_id != old.session_id OR new.unit_id != old.unit_id
        OR new.predecessor_active_recall_run_id != old.predecessor_active_recall_run_id
        OR new.predecessor_action_id IS NOT old.predecessor_action_id
        OR new.kind != old.kind OR new.reason_code != old.reason_code
        OR new.policy_version != old.policy_version OR new.created_at != old.created_at
        THEN RAISE(ABORT, 'adaptive action identity is immutable') END;
    SELECT CASE WHEN new.status = 'completed' AND new.kind = 'remediate'
        AND NOT EXISTS (
            SELECT 1 FROM study_sessions s
            WHERE s.id = new.session_id AND s.course_id = new.course_id
              AND s.status = 'practicing' AND s.current_unit_id = new.unit_id
              AND s.adaptive_policy_version = new.policy_version
        ) THEN RAISE(ABORT, 'remediation completion is outside the current session action') END;
    SELECT CASE WHEN new.status = 'completed' AND new.kind = 'practice'
        AND NOT EXISTS (
            SELECT 1 FROM study_practice_runs pr
            WHERE pr.id = new.practice_run_id
              AND pr.course_id = new.course_id AND pr.session_id = new.session_id
              AND pr.unit_id = new.unit_id
              AND pr.predecessor_active_recall_run_id = new.predecessor_active_recall_run_id
              AND pr.status = 'pending'
        ) THEN RAISE(ABORT, 'adaptive practice action has no matching practice run') END;
END;

CREATE TRIGGER study_adaptive_actions_no_delete
BEFORE DELETE ON study_adaptive_actions BEGIN
    SELECT RAISE(ABORT, 'adaptive action ledger is immutable');
END;

CREATE TRIGGER study_sessions_cancel_pending_adaptive_actions
AFTER UPDATE OF status ON study_sessions
WHEN new.status IN ('completed', 'cancelled', 'failed') BEGIN
    UPDATE study_adaptive_actions
    SET status = 'cancelled', revision = revision + 1,
        cancelled_at = COALESCE(new.finished_at, new.updated_at)
    WHERE session_id = new.id AND status = 'pending';
END;
