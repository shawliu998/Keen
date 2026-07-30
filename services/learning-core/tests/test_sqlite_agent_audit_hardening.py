from __future__ import annotations

import asyncio
import sqlite3

import pytest
from pydantic import ValidationError

from app.agent import (
    AgentStepExecutor,
    SQLiteAuditSink,
    ToolContext,
    ToolRegistry,
    UndoExecutor,
    default_undo_registry,
)
from app.agent.tools.product import CompleteStudyTaskTool
from app.database import Database
from app.repositories.agent_repository import AgentRepository
from app.repositories.task_repository import TaskRepository


_COMPLETE_ARGUMENTS = {
    "task_id": "task-hardening",
    "course_id": "course-hardening",
    "expected_revision": 0,
    "completed_at": "2026-07-16T12:00:00+00:00",
}


def _setup(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO courses (id, title, description, created_at)
        VALUES ('course-hardening', 'Hardening', '', '2026-07-16T00:00:00+00:00')
        """
    )
    connection.commit()
    TaskRepository(connection).create_task(
        task_id="task-hardening",
        course_id="course-hardening",
        title="Review limits",
        reason="Due",
        due_at="2026-07-20T00:00:00+00:00",
        estimated_minutes=20,
        source_type="manual",
        source_id=None,
        priority_score=1.0,
        priority_components={"deadline": 1.0},
        recommended_reason="Due soon",
        idempotency_key="task-hardening-create",
        created_at="2026-07-16T00:00:00+00:00",
    )
    repository = AgentRepository(connection)
    repository.create_run(
        run_id="run-hardening",
        kind="conversation",
        provider="local",
        model="fixture",
        user_intent="Harden undo",
        mode="study",
        prompt_version="v1",
        input_data={},
        idempotency_key="run-hardening",
    )
    repository.transition_run("run-hardening", status="running")
    for ordinal, step_id in enumerate(
        ("step-complete", "step-undo", "step-fake", "step-legacy")
    ):
        repository.add_step(
            step_id=step_id,
            run_id="run-hardening",
            ordinal=ordinal,
            kind="tool",
            label=step_id,
            input_data={},
        )


def _complete_task(connection: sqlite3.Connection) -> dict:
    registry = ToolRegistry()
    registry.register(CompleteStudyTaskTool())
    sink = SQLiteAuditSink(connection)
    asyncio.run(
        AgentStepExecutor(
            registry, sink, transaction_factory=sink.transaction
        ).execute_step(
            invocation_id="invocation-original",
            idempotency_key="original",
            tool_name="complete_study_task",
            arguments=_COMPLETE_ARGUMENTS,
            context=ToolContext(
                run_id="run-hardening",
                step_id="step-complete",
                cancellation_event=asyncio.Event(),
            ),
        )
    )
    return AgentRepository(connection).list_state_mutations("invocation-original")[0]


def _succeed_fake_undo(
    repository: AgentRepository,
    *,
    invocation_id: str,
    mutation_id: str,
    mutations: list,
) -> None:
    repository.start_tool_invocation(
        invocation_id=invocation_id,
        run_id="run-hardening",
        step_id="step-fake",
        tool_name="undo_state_mutation",
        permission_level=2,
        arguments={"mutation_id": mutation_id},
        idempotency_key=invocation_id,
    )
    repository.complete_tool_invocation(
        invocation_id,
        result_summary={"status": "undone"},
        mutations=mutations,
    )


def _raw_mark(
    connection: sqlite3.Connection, *, mutation_id: str, invocation_id: str
) -> None:
    connection.execute(
        """
        UPDATE state_mutations
        SET undone_at = '2026-07-16T15:00:00+00:00',
            undone_by_tool_invocation_id = ?
        WHERE id = ?
        """,
        (invocation_id, mutation_id),
    )


def test_repository_and_trigger_reject_original_no_inverse_and_wrong_target(tmp_path):
    database = Database(tmp_path / "undo-forgery.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup(connection)
        original = _complete_task(connection)
        repository = AgentRepository(connection)

        with pytest.raises(sqlite3.IntegrityError, match="tracking must start empty"):
            connection.execute(
                """
                INSERT INTO state_mutations (
                    id, run_id, tool_invocation_id, ordinal, entity_type,
                    entity_id, operation, before_json, after_json, undo_json,
                    reversible, created_at, undone_at,
                    undone_by_tool_invocation_id
                ) VALUES (
                    'pretracked-forgery', 'run-hardening',
                    'invocation-original', 1, 'study_task', 'task-hardening',
                    'update', '{}', '{}', '{"operation":"update"}', 1,
                    '2026-07-16T15:00:00+00:00',
                    '2026-07-16T15:00:00+00:00', 'invocation-original'
                )
                """
            )
        connection.rollback()
        for mutation_id, undone_at, undone_by in (
            ("pretracked-time-only", "2026-07-16T15:00:00+00:00", None),
            ("pretracked-link-only", None, "invocation-original"),
        ):
            with pytest.raises(
                sqlite3.IntegrityError, match="tracking must start empty"
            ):
                connection.execute(
                    """
                    INSERT INTO state_mutations (
                        id, run_id, tool_invocation_id, ordinal, entity_type,
                        entity_id, operation, before_json, after_json, undo_json,
                        reversible, created_at, undone_at,
                        undone_by_tool_invocation_id
                    ) VALUES (
                        ?, 'run-hardening', 'invocation-original', 1,
                        'study_task', 'task-hardening', 'update', '{}', '{}',
                        '{"operation":"update"}', 1,
                        '2026-07-16T15:00:00+00:00', ?, ?
                    )
                    """,
                    (mutation_id, undone_at, undone_by),
                )
            connection.rollback()

        with pytest.raises(PermissionError, match="dedicated"):
            repository.mark_state_mutation_undone(
                original["id"],
                undo_invocation_id="invocation-original",
            )
        with pytest.raises(sqlite3.IntegrityError, match="recorded inverse"):
            _raw_mark(
                connection,
                mutation_id=original["id"],
                invocation_id="invocation-original",
            )
        connection.rollback()

        _succeed_fake_undo(
            repository,
            invocation_id="fake-no-inverse",
            mutation_id=original["id"],
            mutations=[],
        )
        with pytest.raises(PermissionError, match="exactly one inverse"):
            repository.mark_state_mutation_undone(
                original["id"], undo_invocation_id="fake-no-inverse"
            )
        with pytest.raises(sqlite3.IntegrityError, match="recorded inverse"):
            _raw_mark(
                connection,
                mutation_id=original["id"],
                invocation_id="fake-no-inverse",
            )
        connection.rollback()

        wrong_after = {
            **original["before"],
            "revision": original["after"]["revision"] + 1,
            "updated_at": "2026-07-16T15:00:00+00:00",
        }
        _succeed_fake_undo(
            repository,
            invocation_id="fake-wrong-target",
            mutation_id=original["id"],
            mutations=[
                {
                    "id": "fake-wrong-mutation",
                    "entity_type": "study_task",
                    "entity_id": "another-task",
                    "operation": "update",
                    "before": original["after"],
                    "after": wrong_after,
                    "undo": {
                        "operation": "update",
                        "entity_type": "study_task",
                        "entity_id": "another-task",
                        "restore": original["after"],
                    },
                    "reversible": True,
                }
            ],
        )
        with pytest.raises(PermissionError, match="recorded inverse"):
            repository.mark_state_mutation_undone(
                original["id"], undo_invocation_id="fake-wrong-target"
            )
        with pytest.raises(sqlite3.IntegrityError, match="recorded inverse"):
            _raw_mark(
                connection,
                mutation_id=original["id"],
                invocation_id="fake-wrong-target",
            )
        connection.rollback()

        correct_after = {
            **original["before"],
            "revision": original["after"]["revision"] + 1,
            "updated_at": "2026-07-16T15:30:00+00:00",
        }
        _succeed_fake_undo(
            repository,
            invocation_id="fake-combined-update",
            mutation_id=original["id"],
            mutations=[
                {
                    "id": "fake-combined-inverse",
                    "entity_type": original["entity_type"],
                    "entity_id": original["entity_id"],
                    "operation": "update",
                    "before": original["after"],
                    "after": correct_after,
                    "undo": {
                        "operation": "update",
                        "entity_type": original["entity_type"],
                        "entity_id": original["entity_id"],
                        "restore": original["after"],
                    },
                    "reversible": True,
                }
            ],
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE state_mutations
                SET created_at = 'FORGED-TIME',
                    undone_at = '2026-07-16T15:30:00+00:00',
                    undone_by_tool_invocation_id = 'fake-combined-update'
                WHERE id = ?
                """,
                (original["id"],),
            )
        connection.rollback()
        assert repository.get_state_mutation(original["id"])["undone_at"] is None


def test_undo_executor_rejects_persisted_body_instruction_mismatch_before_write(
    tmp_path,
):
    database = Database(tmp_path / "undo-malformed-row.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup(connection)
        repository = AgentRepository(connection)
        before = TaskRepository(connection).get("task-hardening")
        after = {
            **before,
            "status": "completed",
            "completed_at": "2026-07-16T12:00:00+00:00",
            "updated_at": "2026-07-16T12:00:00+00:00",
            "revision": 1,
        }
        repository.start_tool_invocation(
            invocation_id="legacy-source",
            run_id="run-hardening",
            step_id="step-legacy",
            tool_name="legacy_local_write",
            permission_level=2,
            arguments={},
            idempotency_key="legacy-source",
        )
        repository.complete_tool_invocation(
            "legacy-source",
            result_summary={"status": "completed"},
            mutations=[
                {
                    "id": "legacy-malformed-mutation",
                    "entity_type": "study_task",
                    "entity_id": "task-hardening",
                    "operation": "update",
                    "before": before,
                    "after": after,
                    "undo": {
                        "operation": "update",
                        "entity_type": "study_task",
                        "entity_id": "another-task",
                        "restore": before,
                    },
                    "reversible": True,
                }
            ],
        )
        sink = SQLiteAuditSink(connection)
        executor = UndoExecutor(sink, default_undo_registry())
        with pytest.raises(ValidationError, match="undo target must match"):
            asyncio.run(
                executor.execute(
                    run_id="run-hardening",
                    step_id="step-undo",
                    mutation_id="legacy-malformed-mutation",
                    invocation_id="legacy-undo-attempt",
                    idempotency_key="legacy-undo-attempt",
                    cancellation_event=asyncio.Event(),
                )
            )
        assert TaskRepository(connection).get("task-hardening") == before
        assert (
            repository.get_state_mutation("legacy-malformed-mutation")["undone_at"]
            is None
        )
        assert (
            repository.get_tool_invocation("legacy-undo-attempt")["status"] == "failed"
        )


def test_tracked_undo_audit_rejects_insert_update_and_delete_tampering(tmp_path):
    database = Database(tmp_path / "undo-tracked-immutable.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup(connection)
        original = _complete_task(connection)
        repository = AgentRepository(connection)
        connection.execute(
            """
            INSERT INTO state_mutations (
                id, run_id, tool_invocation_id, ordinal, entity_type,
                entity_id, operation, before_json, after_json, undo_json,
                reversible, created_at
            ) VALUES (
                'preexisting-original-sibling', 'run-hardening',
                'invocation-original', 1, 'study_task', 'sibling-task',
                'update', '{}', '{}', '{"operation":"update"}', 1,
                '2026-07-16T15:30:00+00:00'
            )
            """
        )
        connection.commit()
        sink = SQLiteAuditSink(connection)
        asyncio.run(
            UndoExecutor(sink, default_undo_registry()).execute(
                run_id="run-hardening",
                step_id="step-undo",
                mutation_id=original["id"],
                invocation_id="real-undo",
                idempotency_key="real-undo",
                cancellation_event=asyncio.Event(),
            )
        )
        inverse = repository.list_state_mutations("real-undo")[0]

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE state_mutations SET entity_id = 'another-task' WHERE id = ?",
                (inverse["id"],),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE state_mutations SET entity_id = 'tampered-sibling'
                WHERE id = 'preexisting-original-sibling'
                """
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                """
                DELETE FROM state_mutations
                WHERE id = 'preexisting-original-sibling'
                """
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="cannot gain"):
            connection.execute(
                """
                INSERT INTO state_mutations (
                    id, run_id, tool_invocation_id, ordinal, entity_type,
                    entity_id, operation, before_json, after_json, undo_json,
                    reversible, created_at
                ) VALUES (
                    'extra-inverse', 'run-hardening', 'real-undo', 1,
                    'study_task', 'task-hardening', 'update', '{}', '{}',
                    '{"operation":"update"}', 1,
                    '2026-07-16T16:00:00+00:00'
                )
                """
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="cannot gain"):
            connection.execute(
                """
                INSERT INTO state_mutations (
                    id, run_id, tool_invocation_id, ordinal, entity_type,
                    entity_id, operation, before_json, after_json, undo_json,
                    reversible, created_at
                ) VALUES (
                    'extra-original-sibling', 'run-hardening',
                    'invocation-original', 2, 'study_task', 'task-hardening',
                    'update', '{}', '{}', '{"operation":"update"}', 1,
                    '2026-07-16T16:00:00+00:00'
                )
                """
            )
        connection.rollback()
        for invocation_id, assignment in (
            ("real-undo", "result_summary_json = '{}'"),
            ("real-undo", "step_id = 'step-fake'"),
            ("real-undo", "updated_at = '2026-07-17T00:00:00+00:00'"),
            ("invocation-original", "result_summary_json = '{}'"),
            ("invocation-original", "step_id = 'step-fake'"),
            (
                "invocation-original",
                "finished_at = '2026-07-17T00:00:00+00:00'",
            ),
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(
                    f"UPDATE tool_invocations SET {assignment} WHERE id = ?",
                    (invocation_id,),
                )
            connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute("DELETE FROM tool_invocations WHERE id = 'real-undo'")
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                "DELETE FROM tool_invocations WHERE id = 'invocation-original'"
            )
        connection.rollback()
