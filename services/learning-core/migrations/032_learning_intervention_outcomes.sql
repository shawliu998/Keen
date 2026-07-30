-- Link each published learning-intervention artifact to the independent
-- deterministic Practice that follows it. Multiple artifacts may precede the
-- same Practice when the learner asks for another approach; this is exposure
-- lineage, not a causal learning-effect claim.
CREATE TABLE learning_intervention_outcomes (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE RESTRICT,
    unit_id TEXT NOT NULL REFERENCES study_units(id) ON DELETE RESTRICT,
    trigger_active_recall_run_id TEXT NOT NULL
        REFERENCES study_active_recall_runs(id) ON DELETE RESTRICT,
    intervention_run_id TEXT NOT NULL
        REFERENCES agent_runs(id) ON DELETE RESTRICT,
    intervention_artifact_id TEXT NOT NULL
        CHECK (length(intervention_artifact_id) BETWEEN 1 AND 128),
    practice_run_id TEXT NOT NULL
        REFERENCES study_practice_runs(id) ON DELETE RESTRICT,
    playbook_slug TEXT NOT NULL CHECK (length(playbook_slug) BETWEEN 1 AND 128),
    playbook_version INTEGER NOT NULL CHECK (playbook_version > 0),
    playbook_definition_hash TEXT NOT NULL CHECK (
        length(playbook_definition_hash) = 64
        AND playbook_definition_hash NOT GLOB '*[^0-9a-f]*'
    ),
    linked_at TEXT NOT NULL,
    UNIQUE (intervention_run_id, intervention_artifact_id)
);

CREATE INDEX learning_intervention_outcomes_session_idx
ON learning_intervention_outcomes(session_id, linked_at, id);

CREATE INDEX learning_intervention_outcomes_practice_idx
ON learning_intervention_outcomes(practice_run_id, linked_at, id);

CREATE TRIGGER learning_intervention_outcomes_relationships_insert
BEFORE INSERT ON learning_intervention_outcomes BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM agent_runs ar
        JOIN study_practice_runs pr ON pr.id = new.practice_run_id
        WHERE ar.id = new.intervention_run_id
          AND ar.kind = 'deep_learn'
          AND ar.mode = 'study'
          AND ar.course_scope_id = new.course_id
          AND ar.study_session_id = new.session_id
          AND json_extract(ar.input_json, '$.intervention.profileId')
              = 'learning.intervention.source-grounded.v1'
          AND json_extract(ar.input_json, '$.intervention.courseId') = new.course_id
          AND json_extract(ar.input_json, '$.intervention.sessionId') = new.session_id
          AND json_extract(ar.input_json, '$.intervention.unitId') = new.unit_id
          AND json_extract(ar.input_json, '$.intervention.triggerRecallRunId')
              = new.trigger_active_recall_run_id
          AND json_extract(ar.input_json, '$.intervention.playbookSlug')
              = new.playbook_slug
          AND json_extract(ar.input_json, '$.intervention.playbookVersion')
              = new.playbook_version
          AND json_extract(ar.input_json, '$.intervention.playbookDefinitionHash')
              = new.playbook_definition_hash
          AND pr.course_id = new.course_id
          AND pr.session_id = new.session_id
          AND pr.unit_id = new.unit_id
          AND pr.predecessor_active_recall_run_id
              = new.trigger_active_recall_run_id
    ) THEN RAISE(ABORT, 'intervention outcome lineage is outside its learning context') END;
END;

CREATE TRIGGER learning_intervention_outcomes_immutable
BEFORE UPDATE ON learning_intervention_outcomes BEGIN
    SELECT RAISE(ABORT, 'intervention outcome lineage is immutable');
END;

CREATE TRIGGER learning_intervention_outcomes_no_delete
BEFORE DELETE ON learning_intervention_outcomes BEGIN
    SELECT RAISE(ABORT, 'intervention outcome lineage is immutable');
END;
