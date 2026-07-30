ALTER TABLE review_schedules
ADD COLUMN fsrs_card_id INTEGER;

WITH numbered AS (
    SELECT
        review_item_id,
        ROW_NUMBER() OVER (ORDER BY review_item_id) AS fsrs_card_id
    FROM review_schedules
)
UPDATE review_schedules
SET fsrs_card_id = (
    SELECT numbered.fsrs_card_id
    FROM numbered
    WHERE numbered.review_item_id = review_schedules.review_item_id
);

UPDATE review_schedules
SET scheduler_version = 'fsrs-6.3.1-keen-v1'
WHERE scheduler = 'fsrs'
  AND state = 'new'
  AND last_reviewed_at IS NULL
  AND repetitions = 0
  AND lapses = 0
  AND stability = 0;

UPDATE review_schedules
SET scheduler_state_json = json_object(
    'card_id', fsrs_card_id,
    'step', CASE
        WHEN state = 'review' THEN NULL
        WHEN json_type(scheduler_state_json, '$.step') = 'integer'
             AND json_extract(scheduler_state_json, '$.step') >= 0
            THEN json_extract(scheduler_state_json, '$.step')
        ELSE 0
    END
)
WHERE scheduler = 'fsrs';

CREATE TABLE review_fsrs_identity_sequence (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    next_card_id INTEGER NOT NULL
        CHECK (typeof(next_card_id) = 'integer' AND next_card_id > 0)
);

INSERT INTO review_fsrs_identity_sequence (singleton, next_card_id)
SELECT
    1,
    CASE
        WHEN COALESCE(MAX(fsrs_card_id), 0) >= 9223372036854775807
            THEN 9223372036854775807
        ELSE COALESCE(MAX(fsrs_card_id), 0) + 1
    END
FROM review_schedules;

CREATE UNIQUE INDEX review_schedules_fsrs_card_id_idx
ON review_schedules(fsrs_card_id);

CREATE TRIGGER review_schedules_fsrs_card_id_insert
BEFORE INSERT ON review_schedules
WHEN new.fsrs_card_id IS NULL
  OR typeof(new.fsrs_card_id) <> 'integer'
  OR new.fsrs_card_id <= 0
BEGIN
    SELECT RAISE(ABORT, 'review schedule FSRS card id must be a positive integer');
END;

CREATE TRIGGER review_schedules_fsrs_card_id_update
BEFORE UPDATE OF fsrs_card_id ON review_schedules
WHEN new.fsrs_card_id IS NULL
  OR typeof(new.fsrs_card_id) <> 'integer'
  OR new.fsrs_card_id <= 0
BEGIN
    SELECT RAISE(ABORT, 'review schedule FSRS card id must be a positive integer');
END;

CREATE TRIGGER review_schedules_fsrs_card_id_immutable
BEFORE UPDATE OF fsrs_card_id ON review_schedules
WHEN new.fsrs_card_id <> old.fsrs_card_id
BEGIN
    SELECT RAISE(ABORT, 'review schedule FSRS card id is immutable');
END;

CREATE TRIGGER review_schedules_fsrs_state_insert
BEFORE INSERT ON review_schedules
WHEN new.scheduler = 'fsrs' AND (
    COALESCE(json_type(new.scheduler_state_json, '$.card_id'), '') <> 'integer'
    OR COALESCE(json_extract(new.scheduler_state_json, '$.card_id'), -1)
       <> new.fsrs_card_id
    OR (SELECT COUNT(*) FROM json_each(new.scheduler_state_json)) <> 2
    OR EXISTS (
        SELECT 1 FROM json_each(new.scheduler_state_json)
        WHERE key NOT IN ('card_id', 'step')
    )
    OR (
        new.state = 'review'
        AND COALESCE(json_type(new.scheduler_state_json, '$.step'), '') <> 'null'
    )
    OR (
        new.state = 'new'
        AND (
            COALESCE(json_type(new.scheduler_state_json, '$.step'), '') <> 'integer'
            OR COALESCE(json_extract(new.scheduler_state_json, '$.step'), -1) <> 0
        )
    )
    OR (
        new.state IN ('learning', 'relearning')
        AND (
            COALESCE(json_type(new.scheduler_state_json, '$.step'), '') <> 'integer'
            OR COALESCE(json_extract(new.scheduler_state_json, '$.step'), -1) < 0
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'review schedule FSRS state is inconsistent');
END;

CREATE TRIGGER review_schedules_fsrs_state_update
BEFORE UPDATE OF fsrs_card_id, scheduler, scheduler_state_json, state
ON review_schedules
WHEN new.scheduler = 'fsrs' AND (
    COALESCE(json_type(new.scheduler_state_json, '$.card_id'), '') <> 'integer'
    OR COALESCE(json_extract(new.scheduler_state_json, '$.card_id'), -1)
       <> new.fsrs_card_id
    OR (SELECT COUNT(*) FROM json_each(new.scheduler_state_json)) <> 2
    OR EXISTS (
        SELECT 1 FROM json_each(new.scheduler_state_json)
        WHERE key NOT IN ('card_id', 'step')
    )
    OR (
        new.state = 'review'
        AND COALESCE(json_type(new.scheduler_state_json, '$.step'), '') <> 'null'
    )
    OR (
        new.state = 'new'
        AND (
            COALESCE(json_type(new.scheduler_state_json, '$.step'), '') <> 'integer'
            OR COALESCE(json_extract(new.scheduler_state_json, '$.step'), -1) <> 0
        )
    )
    OR (
        new.state IN ('learning', 'relearning')
        AND (
            COALESCE(json_type(new.scheduler_state_json, '$.step'), '') <> 'integer'
            OR COALESCE(json_extract(new.scheduler_state_json, '$.step'), -1) < 0
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'review schedule FSRS state is inconsistent');
END;
