-- Persist the exact Feed task that initiated a Review rating.  A nullable
-- column preserves direct Review ratings made outside the task queue.
ALTER TABLE review_attempts
ADD COLUMN originating_task_id TEXT
    REFERENCES study_tasks(id) ON DELETE RESTRICT;

CREATE INDEX review_attempts_originating_task_idx
ON review_attempts(originating_task_id)
WHERE originating_task_id IS NOT NULL;

-- A persisted queue task represents one review handoff and may be consumed
-- by at most one rating attempt.
CREATE UNIQUE INDEX review_attempts_originating_task_unique
ON review_attempts(originating_task_id)
WHERE originating_task_id IS NOT NULL;
