ALTER TABLE state_mutations ADD COLUMN undone_at TEXT;
ALTER TABLE state_mutations ADD COLUMN undone_by_tool_invocation_id TEXT
    REFERENCES tool_invocations(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX state_mutations_undone_by_idx
    ON state_mutations(undone_by_tool_invocation_id)
    WHERE undone_by_tool_invocation_id IS NOT NULL;

CREATE TRIGGER state_mutations_undo_tracking_insert
BEFORE INSERT ON state_mutations WHEN new.undone_at IS NOT NULL
    OR new.undone_by_tool_invocation_id IS NOT NULL BEGIN
    SELECT RAISE(ABORT, 'state mutation undo tracking must start empty');
END;

CREATE TRIGGER state_mutations_undo_tracking_update
BEFORE UPDATE OF undone_at, undone_by_tool_invocation_id ON state_mutations BEGIN
    SELECT CASE WHEN (new.undone_at IS NULL) != (new.undone_by_tool_invocation_id IS NULL)
        THEN RAISE(ABORT, 'undo timestamp and invocation must be set together') END;
    SELECT CASE WHEN old.undone_at IS NOT NULL
        THEN RAISE(ABORT, 'a state mutation can only be undone once') END;
    SELECT CASE WHEN new.undone_by_tool_invocation_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM tool_invocations undo_invocation
        JOIN state_mutations inverse
          ON inverse.tool_invocation_id = undo_invocation.id
        WHERE undo_invocation.id = new.undone_by_tool_invocation_id
          AND undo_invocation.id != new.tool_invocation_id
          AND undo_invocation.run_id = new.run_id
          AND undo_invocation.permission_level = 2
          AND undo_invocation.status = 'succeeded'
          AND undo_invocation.tool_name = 'undo_state_mutation'
          AND json_extract(undo_invocation.arguments_json, '$.mutation_id') = new.id
          AND (
              SELECT count(*) FROM state_mutations counted
              WHERE counted.tool_invocation_id = undo_invocation.id
          ) = 1
          AND new.entity_type = 'study_task'
          AND new.operation = 'update'
          AND json_extract(new.undo_json, '$.operation') = 'update'
          AND json_extract(new.undo_json, '$.entity_type') = new.entity_type
          AND json_extract(new.undo_json, '$.entity_id') = new.entity_id
          AND json(json_extract(new.undo_json, '$.restore')) = json(new.before_json)
          AND inverse.run_id = new.run_id
          AND inverse.entity_type = new.entity_type
          AND inverse.entity_id = new.entity_id
          AND inverse.operation = json_extract(new.undo_json, '$.operation')
          AND json_extract(inverse.undo_json, '$.operation') = new.operation
          AND json_extract(inverse.undo_json, '$.entity_type') = new.entity_type
          AND json_extract(inverse.undo_json, '$.entity_id') = new.entity_id
          AND json_type(new.before_json) = 'object'
          AND json_type(new.after_json) = 'object'
          AND json_type(inverse.before_json) = 'object'
          AND json_type(inverse.after_json) = 'object'
          AND json(inverse.before_json) = json(new.after_json)
          AND json_remove(inverse.after_json, '$.revision', '$.updated_at')
              = json_remove(new.before_json, '$.revision', '$.updated_at')
          AND json_extract(inverse.after_json, '$.revision')
              = json_extract(new.after_json, '$.revision') + 1
          AND json(json_extract(inverse.undo_json, '$.restore'))
              = json(inverse.before_json)
    ) THEN RAISE(ABORT, 'undo invocation does not contain the recorded inverse mutation') END;
END;

CREATE TRIGGER state_mutations_tracked_inverse_insert
BEFORE INSERT ON state_mutations WHEN EXISTS (
    SELECT 1 FROM state_mutations original
    WHERE original.undone_by_tool_invocation_id = new.tool_invocation_id
       OR (
           original.tool_invocation_id = new.tool_invocation_id
           AND original.undone_at IS NOT NULL
       )
) BEGIN
    SELECT RAISE(ABORT, 'tracked undo invocation cannot gain another mutation');
END;

CREATE TRIGGER state_mutations_tracked_audit_update
BEFORE UPDATE OF id, run_id, tool_invocation_id, ordinal, entity_type, entity_id,
                 operation, before_json, after_json, undo_json, reversible, created_at
ON state_mutations WHEN old.undone_at IS NOT NULL OR EXISTS (
    SELECT 1 FROM state_mutations original
    WHERE original.undone_by_tool_invocation_id = old.tool_invocation_id
       OR (
           original.tool_invocation_id = old.tool_invocation_id
           AND original.undone_at IS NOT NULL
       )
) OR new.undone_at IS NOT NULL
  OR new.undone_by_tool_invocation_id IS NOT NULL BEGIN
    SELECT RAISE(ABORT, 'tracked undo mutations are immutable');
END;

CREATE TRIGGER state_mutations_tracked_audit_delete
BEFORE DELETE ON state_mutations WHEN old.undone_at IS NOT NULL OR EXISTS (
    SELECT 1 FROM state_mutations original
    WHERE original.undone_by_tool_invocation_id = old.tool_invocation_id
       OR (
           original.tool_invocation_id = old.tool_invocation_id
           AND original.undone_at IS NOT NULL
       )
) BEGIN
    SELECT RAISE(ABORT, 'tracked undo mutations cannot be deleted');
END;

CREATE TRIGGER tool_invocations_tracked_undo_update
BEFORE UPDATE ON tool_invocations WHEN EXISTS (
    SELECT 1 FROM state_mutations original
    WHERE original.undone_by_tool_invocation_id = old.id
       OR (original.tool_invocation_id = old.id AND original.undone_at IS NOT NULL)
) BEGIN
    SELECT RAISE(ABORT, 'tracked undo invocation is immutable');
END;

CREATE TRIGGER tool_invocations_tracked_undo_delete
BEFORE DELETE ON tool_invocations WHEN EXISTS (
    SELECT 1 FROM state_mutations original
    WHERE original.undone_by_tool_invocation_id = old.id
       OR (original.tool_invocation_id = old.id AND original.undone_at IS NOT NULL)
) BEGIN
    SELECT RAISE(ABORT, 'tracked undo invocation cannot be deleted');
END;
