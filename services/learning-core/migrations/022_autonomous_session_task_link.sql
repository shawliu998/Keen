-- Keep an autonomous session's originating task as a real, course-scoped
-- relationship.  JSON goal scope is useful display metadata, but cannot
-- enforce idempotency or prevent cross-course links.
ALTER TABLE study_sessions
ADD COLUMN originating_task_id TEXT REFERENCES study_tasks(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX study_sessions_originating_task_idx
ON study_sessions(originating_task_id)
WHERE originating_task_id IS NOT NULL;

CREATE TRIGGER study_sessions_originating_task_course_insert
BEFORE INSERT ON study_sessions
WHEN new.originating_task_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_tasks t
        WHERE t.id = new.originating_task_id
          AND t.course_id = new.course_id
    ) THEN RAISE(ABORT, 'originating task does not belong to study-session course') END;
END;

CREATE TRIGGER study_sessions_originating_task_course_update
BEFORE UPDATE OF originating_task_id, course_id ON study_sessions
WHEN new.originating_task_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM study_tasks t
        WHERE t.id = new.originating_task_id
          AND t.course_id = new.course_id
    ) THEN RAISE(ABORT, 'originating task does not belong to study-session course') END;
END;

-- The relationship must remain scoped when the task is edited too.  Checking
-- only writes to study_sessions would allow a later task course update to
-- leave an already-linked session pointing across courses.
CREATE TRIGGER study_tasks_originating_session_course_update
BEFORE UPDATE OF course_id ON study_tasks
WHEN EXISTS (
    SELECT 1 FROM study_sessions s
    WHERE s.originating_task_id = old.id
      AND s.course_id <> new.course_id
) BEGIN
    SELECT RAISE(ABORT, 'originating task course cannot differ from linked study session');
END;
