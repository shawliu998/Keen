-- Preserve every legacy course row exactly as it is.  In particular, do not
-- backfill normalized_title: existing databases can contain duplicate titles.
-- New writes are indexed while the repository also scans legacy titles under
-- its BEGIN IMMEDIATE transaction.
ALTER TABLE courses ADD COLUMN normalized_title TEXT;

CREATE UNIQUE INDEX courses_normalized_title_unique
ON courses(normalized_title)
WHERE normalized_title IS NOT NULL;

CREATE TABLE course_create_idempotency (
    idempotency_key TEXT PRIMARY KEY
        CHECK (length(idempotency_key) BETWEEN 16 AND 200),
    canonical_payload_json TEXT NOT NULL
        CHECK (json_valid(canonical_payload_json)
              AND json_type(canonical_payload_json) = 'object'),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);
