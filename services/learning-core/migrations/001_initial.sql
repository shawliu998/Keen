CREATE TABLE courses (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE concepts (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    bkt_slip REAL NOT NULL DEFAULT 0.1 CHECK (bkt_slip BETWEEN 0 AND 1),
    bkt_guess REAL NOT NULL DEFAULT 0.2 CHECK (bkt_guess BETWEEN 0 AND 1),
    bkt_transit REAL NOT NULL DEFAULT 0.1 CHECK (bkt_transit BETWEEN 0 AND 1),
    UNIQUE(course_id, name)
);

CREATE TABLE mastery (
    concept_id TEXT PRIMARY KEY REFERENCES concepts(id) ON DELETE CASCADE,
    probability REAL NOT NULL CHECK (probability BETWEEN 0 AND 1),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE mastery_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    probability_before REAL NOT NULL CHECK (probability_before BETWEEN 0 AND 1),
    probability_after REAL NOT NULL CHECK (probability_after BETWEEN 0 AND 1),
    observed_at TEXT NOT NULL
);

CREATE TABLE study_tasks (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    concept_id TEXT REFERENCES concepts(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    reason TEXT NOT NULL,
    due_at TEXT NOT NULL,
    estimated_minutes INTEGER NOT NULL CHECK (estimated_minutes > 0),
    status TEXT NOT NULL CHECK (status IN ('upcoming', 'overdue', 'completed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX study_tasks_due_idx ON study_tasks(status, due_at);
CREATE INDEX concepts_course_idx ON concepts(course_id);
CREATE INDEX mastery_events_concept_idx ON mastery_events(concept_id, observed_at);
