-- One immutable bridge records the deterministic study recap and the real
-- FSRS card created from an answered targeted-practice assessment.
CREATE TABLE study_summary_review_handoffs (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL UNIQUE REFERENCES study_sessions(id) ON DELETE RESTRICT,
    unit_id TEXT NOT NULL REFERENCES study_units(id) ON DELETE RESTRICT,
    practice_run_id TEXT NOT NULL UNIQUE REFERENCES study_practice_runs(id) ON DELETE RESTRICT,
    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE RESTRICT,
    item_id TEXT NOT NULL REFERENCES assessment_items(id) ON DELETE RESTRICT,
    concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE RESTRICT,
    review_item_id TEXT NOT NULL UNIQUE REFERENCES review_items(id) ON DELETE RESTRICT,
    active_recall_correct INTEGER NOT NULL CHECK (active_recall_correct IN (0, 1)),
    practice_correct INTEGER NOT NULL CHECK (practice_correct IN (0, 1)),
    practice_score REAL NOT NULL CHECK (practice_score >= 0 AND practice_score <= 1),
    practice_max_score REAL NOT NULL CHECK (practice_max_score > 0 AND practice_max_score <= 1),
    remaining_units INTEGER NOT NULL CHECK (remaining_units >= 0 AND remaining_units <= 7),
    scheduler_version TEXT NOT NULL CHECK (length(scheduler_version) BETWEEN 1 AND 128),
    review_due_at TEXT NOT NULL,
    review_scheduler TEXT NOT NULL CHECK (review_scheduler = 'fsrs'),
    review_state TEXT NOT NULL CHECK (review_state = 'new'),
    originating_task_id TEXT REFERENCES study_tasks(id) ON DELETE RESTRICT,
    task_completed INTEGER NOT NULL CHECK (task_completed IN (0, 1)),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (
        length(idempotency_key) BETWEEN 16 AND 128
        AND idempotency_key NOT GLOB '*[^A-Za-z0-9._:-]*'
    ),
    payload_fingerprint TEXT NOT NULL CHECK (
        length(payload_fingerprint) = 64
        AND payload_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL
);

CREATE INDEX study_summary_review_handoffs_course_created_idx
ON study_summary_review_handoffs(course_id, created_at, id);

CREATE TRIGGER study_summary_review_handoffs_insert
BEFORE INSERT ON study_summary_review_handoffs BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM study_sessions s
        JOIN study_units u ON u.id = new.unit_id
        JOIN study_plan_versions p ON p.id = u.plan_version_id
        JOIN study_practice_runs r ON r.id = new.practice_run_id
        JOIN assessment_items i ON i.id = new.item_id AND i.assessment_id = new.assessment_id
        JOIN answer_evaluations ev ON ev.id = r.evaluation_id AND ev.item_id = i.id
        JOIN study_active_recall_runs ar ON ar.id = r.predecessor_active_recall_run_id
        JOIN answer_evaluations arev ON arev.id = ar.evaluation_id
        JOIN review_items ri ON ri.id = new.review_item_id
        JOIN review_schedules rs ON rs.review_item_id = ri.id
        WHERE s.id = new.session_id AND s.course_id = new.course_id
          AND s.status = 'review_scheduling' AND s.current_unit_id = u.id
          AND p.session_id = s.id AND u.concept_id = new.concept_id
          AND r.course_id = new.course_id AND r.session_id = new.session_id
          AND r.unit_id = new.unit_id AND r.concept_id = new.concept_id
          AND r.assessment_id = new.assessment_id AND r.item_id = new.item_id
          AND r.status = 'answered'
          AND new.active_recall_correct = arev.is_correct
          AND new.practice_correct = ev.is_correct
          AND abs(new.practice_score - ev.final_score) <= 0.0000005
          AND abs(new.practice_max_score - i.max_score) <= 0.0000005
          AND ri.course_id = new.course_id AND ri.concept_id = new.concept_id
          AND ri.item_type = 'practice_problem' AND ri.source_type = 'assessment'
          AND ri.source_id = new.assessment_id AND ri.status = 'active'
          AND rs.scheduler = 'fsrs' AND rs.scheduler_version = new.scheduler_version
          AND rs.state = 'new' AND rs.repetitions = 0 AND rs.lapses = 0
          AND rs.due_at = new.review_due_at AND new.review_scheduler = rs.scheduler
          AND new.review_state = rs.state
          AND (
              (new.originating_task_id IS NULL AND new.task_completed = 0)
              OR EXISTS (
                  SELECT 1 FROM study_tasks t WHERE t.id = new.originating_task_id
                    AND t.course_id = new.course_id AND t.status = 'completed'
                    AND new.task_completed = 1
              )
          )
    ) THEN RAISE(ABORT, 'summary handoff lineage is invalid') END;
END;

CREATE TRIGGER study_summary_review_handoffs_immutable
BEFORE UPDATE ON study_summary_review_handoffs BEGIN
    SELECT RAISE(ABORT, 'summary handoff is immutable');
END;
CREATE TRIGGER study_summary_review_handoffs_no_delete
BEFORE DELETE ON study_summary_review_handoffs BEGIN
    SELECT RAISE(ABORT, 'summary handoff is immutable');
END;

CREATE TRIGGER study_sessions_summary_handoff_completion_guard
BEFORE UPDATE OF status ON study_sessions
WHEN old.status = 'review_scheduling' AND new.status = 'completed'
 AND NOT EXISTS (SELECT 1 FROM study_summary_review_handoffs WHERE session_id = old.id)
BEGIN SELECT RAISE(ABORT, 'review scheduling requires a summary handoff'); END;

CREATE TRIGGER study_sessions_summary_active_unit_completion_guard
BEFORE UPDATE OF status ON study_sessions
WHEN old.status = 'review_scheduling' AND new.status = 'completed'
 AND (
    EXISTS (
        SELECT 1 FROM study_units u JOIN study_plan_versions p ON p.id = u.plan_version_id
        WHERE p.session_id = old.id AND u.status = 'active'
    )
    OR old.current_unit_id IS NOT NULL
 )
BEGIN SELECT RAISE(ABORT, 'completed study session requires completed current unit'); END;

CREATE TRIGGER study_sessions_summary_handoff_course_immutable
BEFORE UPDATE OF course_id ON study_sessions
WHEN new.course_id != old.course_id
 AND EXISTS (SELECT 1 FROM study_summary_review_handoffs WHERE session_id = old.id)
BEGIN SELECT RAISE(ABORT, 'summary handoff session course is immutable'); END;
