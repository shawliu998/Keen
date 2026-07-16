from __future__ import annotations

import asyncio
import concurrent.futures
import sqlite3
import threading

import pytest

from app.agent import (
    AgentStepExecutor,
    InFlightInvocationError,
    PermissionLevel,
    SQLiteAuditSink,
    SQLiteToolSession,
    ToolArguments,
    ToolAuditStart,
    ToolContext,
    ToolEffect,
    ToolRegistry,
    ToolReplayResult,
    ToolResult,
    TerminalInvocationError,
    UndoExecutor,
    default_undo_registry,
    summarize_for_audit,
)
from app.agent.tools.product import CompleteStudyTaskTool
from app.database import Database
from app.repositories.agent_repository import AgentRepository
from app.repositories.task_repository import TaskRepository


def _setup_state(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO courses (id, title, description, created_at)
        VALUES ('course-audit', 'Audit', '', '2026-07-16T00:00:00+00:00')
        """
    )
    connection.commit()
    TaskRepository(connection).create_task(
        task_id="task-audit",
        course_id="course-audit",
        title="Review limits",
        reason="Due",
        due_at="2026-07-20T00:00:00+00:00",
        estimated_minutes=20,
        source_type="manual",
        source_id=None,
        priority_score=1.0,
        priority_components={"deadline": 1.0},
        recommended_reason="Due soon",
        idempotency_key="task-audit-create",
        created_at="2026-07-16T00:00:00+00:00",
    )
    repository = AgentRepository(connection)
    repository.create_run(
        run_id="run-audit",
        kind="conversation",
        provider="local",
        model="fixture",
        user_intent="Complete a task",
        mode="study",
        prompt_version="v1",
        input_data={},
        idempotency_key="run-audit",
    )
    repository.transition_run("run-audit", status="running")
    for ordinal, step_id in enumerate(("step-tool", "step-undo", "step-redo")):
        repository.add_step(
            step_id=step_id,
            run_id="run-audit",
            ordinal=ordinal,
            kind="tool",
            label=step_id,
            input_data={},
        )


def _executor(connection: sqlite3.Connection) -> AgentStepExecutor:
    registry = ToolRegistry()
    registry.register(CompleteStudyTaskTool())
    sink = SQLiteAuditSink(connection)
    return AgentStepExecutor(
        registry,
        sink,
        transaction_factory=sink.transaction,
    )


def _context(step_id: str = "step-tool") -> ToolContext:
    return ToolContext(
        run_id="run-audit",
        step_id=step_id,
        cancellation_event=asyncio.Event(),
    )


_COMPLETE_ARGUMENTS = {
    "task_id": "task-audit",
    "course_id": "course-audit",
    "expected_revision": 0,
    "completed_at": "2026-07-16T12:00:00+00:00",
}


class _CommitThenRaiseConnection(sqlite3.Connection):
    raise_after_next_commit = False

    def commit(self) -> None:
        super().commit()
        if self.raise_after_next_commit:
            self.raise_after_next_commit = False
            raise RuntimeError("driver raised after durable commit")


def _fault_connection(database: Database) -> _CommitThenRaiseConnection:
    connection = sqlite3.connect(
        database.path,
        timeout=10.0,
        factory=_CommitThenRaiseConnection,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


class _ArmCommitFailureSink(SQLiteAuditSink):
    async def record_succeeded(self, record, *, mutations, transaction) -> None:
        await super().record_succeeded(
            record, mutations=mutations, transaction=transaction
        )
        assert isinstance(self.connection, _CommitThenRaiseConnection)
        self.connection.raise_after_next_commit = True


def test_commit_after_apply_is_reconciled_as_success_and_replays(tmp_path):
    database = Database(tmp_path / "audit-commit-applied.sqlite3")
    database.migrate()
    connection = _fault_connection(database)
    try:
        _setup_state(connection)
        registry = ToolRegistry()
        registry.register(CompleteStudyTaskTool())
        sink = _ArmCommitFailureSink(
            connection,
            reconciliation_connection_factory=database.connection,
        )
        result = asyncio.run(
            AgentStepExecutor(
                registry, sink, transaction_factory=sink.transaction
            ).execute_step(
                invocation_id="invocation-ambiguous-commit",
                idempotency_key="ambiguous-commit",
                tool_name="complete_study_task",
                arguments=_COMPLETE_ARGUMENTS,
                context=_context(),
            )
        )
        assert isinstance(result, ToolResult)
    finally:
        connection.close()

    with database.connection() as durable:
        repository = AgentRepository(durable)
        assert TaskRepository(durable).get("task-audit")["status"] == "completed"
        assert (
            repository.get_tool_invocation("invocation-ambiguous-commit")["status"]
            == "succeeded"
        )
        assert len(repository.list_state_mutations("invocation-ambiguous-commit")) == 1
        replay = asyncio.run(
            _executor(durable).execute_step(
                invocation_id="invocation-ambiguous-retry",
                idempotency_key="ambiguous-commit",
                tool_name="complete_study_task",
                arguments=_COMPLETE_ARGUMENTS,
                context=_context(),
            )
        )
        assert isinstance(replay, ToolReplayResult)
        assert replay.result_summary == {
            "revision": 1,
            "status": "completed",
            "task_id": "task-audit",
        }


def test_reservation_commit_after_apply_is_terminalized_without_execution(tmp_path):
    database = Database(tmp_path / "audit-reservation-applied.sqlite3")
    database.migrate()
    connection = _fault_connection(database)
    try:
        _setup_state(connection)
        connection.raise_after_next_commit = True
        registry = ToolRegistry()
        registry.register(CompleteStudyTaskTool())
        sink = SQLiteAuditSink(
            connection,
            reconciliation_connection_factory=database.connection,
        )
        with pytest.raises(TerminalInvocationError, match="durably failed"):
            asyncio.run(
                AgentStepExecutor(
                    registry, sink, transaction_factory=sink.transaction
                ).execute_step(
                    invocation_id="invocation-reservation-uncertain",
                    idempotency_key="reservation-uncertain",
                    tool_name="complete_study_task",
                    arguments=_COMPLETE_ARGUMENTS,
                    context=_context(),
                )
            )
    finally:
        connection.close()

    with database.connection() as durable:
        repository = AgentRepository(durable)
        assert (
            repository.get_tool_invocation("invocation-reservation-uncertain")["status"]
            == "failed"
        )
        assert (
            repository.get_tool_invocation("invocation-reservation-uncertain")[
                "error_code"
            ]
            == "reservation_commit_uncertain"
        )
        assert TaskRepository(durable).get("task-audit")["status"] == "upcoming"
        with pytest.raises(TerminalInvocationError, match="new idempotency key"):
            asyncio.run(
                _executor(durable).execute_step(
                    invocation_id="invocation-reservation-retry",
                    idempotency_key="reservation-uncertain",
                    tool_name="complete_study_task",
                    arguments=_COMPLETE_ARGUMENTS,
                    context=_context(),
                )
            )


def test_completed_level_two_replays_after_restart_without_repeating_write(tmp_path):
    database = Database(tmp_path / "audit-replay.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        result = asyncio.run(
            _executor(connection).execute_step(
                invocation_id="invocation-complete",
                idempotency_key="complete-once",
                tool_name="complete_study_task",
                arguments=_COMPLETE_ARGUMENTS,
                context=_context(),
            )
        )
        assert isinstance(result, ToolResult)
        assert TaskRepository(connection).get("task-audit")["revision"] == 1
        assert (
            connection.execute("SELECT count(*) FROM state_mutations").fetchone()[0]
            == 1
        )

    with database.connection() as restarted:
        replay = asyncio.run(
            _executor(restarted).execute_step(
                invocation_id="invocation-ignored-on-replay",
                idempotency_key="complete-once",
                tool_name="complete_study_task",
                arguments=_COMPLETE_ARGUMENTS,
                context=_context(),
            )
        )
        assert isinstance(replay, ToolReplayResult)
        assert replay.invocation_id == "invocation-complete"
        assert replay.result_summary == {
            "revision": 1,
            "status": "completed",
            "task_id": "task-audit",
        }
        assert len(replay.mutation_ids) == 1
        assert TaskRepository(restarted).get("task-audit")["revision"] == 1
        assert (
            restarted.execute("SELECT count(*) FROM state_mutations").fetchone()[0] == 1
        )


def test_same_idempotency_key_rejects_different_payload_and_in_flight_work(tmp_path):
    database = Database(tmp_path / "audit-conflict.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        asyncio.run(
            _executor(connection).execute_step(
                invocation_id="invocation-complete",
                idempotency_key="complete-once",
                tool_name="complete_study_task",
                arguments=_COMPLETE_ARGUMENTS,
                context=_context(),
            )
        )
        with pytest.raises(ValueError, match="different tool arguments"):
            asyncio.run(
                _executor(connection).execute_step(
                    invocation_id="invocation-conflict",
                    idempotency_key="complete-once",
                    tool_name="complete_study_task",
                    arguments={
                        **_COMPLETE_ARGUMENTS,
                        "completed_at": "2026-07-16T13:00:00+00:00",
                    },
                    context=_context(),
                )
            )

    database = Database(tmp_path / "audit-in-flight.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        validated = CompleteStudyTaskTool.arguments_model.model_validate(
            _COMPLETE_ARGUMENTS
        )
        summary = summarize_for_audit(validated.model_dump(mode="json"))
        asyncio.run(
            SQLiteAuditSink(connection).record_started(
                ToolAuditStart(
                    invocation_id="invocation-running",
                    run_id="run-audit",
                    step_id="step-tool",
                    tool_name="complete_study_task",
                    permission_level=PermissionLevel.LOCAL_REVERSIBLE,
                    arguments=summary,
                    idempotency_key="running-key",
                )
            )
        )
        with pytest.raises(InFlightInvocationError, match="in flight"):
            asyncio.run(
                _executor(connection).execute_step(
                    invocation_id="invocation-duplicate",
                    idempotency_key="running-key",
                    tool_name="complete_study_task",
                    arguments=_COMPLETE_ARGUMENTS,
                    context=_context(),
                )
            )
        assert TaskRepository(connection).get("task-audit")["status"] == "upcoming"


def test_two_connections_concurrently_claim_one_idempotent_level_two_write(tmp_path):
    database = Database(tmp_path / "audit-concurrent.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)

    def run_one(invocation_id: str, completed_at: str, barrier: threading.Barrier):
        with database.connection() as connection:
            barrier.wait(timeout=2)
            try:
                return asyncio.run(
                    _executor(connection).execute_step(
                        invocation_id=invocation_id,
                        idempotency_key="concurrent-key",
                        tool_name="complete_study_task",
                        arguments={**_COMPLETE_ARGUMENTS, "completed_at": completed_at},
                        context=_context(),
                    )
                )
            except Exception as error:
                return error

    same_payload_barrier = threading.Barrier(2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        same_results = list(
            pool.map(
                lambda invocation_id: run_one(
                    invocation_id,
                    "2026-07-16T12:00:00+00:00",
                    same_payload_barrier,
                ),
                ("concurrent-a", "concurrent-b"),
            )
        )
    assert sum(isinstance(result, ToolResult) for result in same_results) == 1
    assert all(
        isinstance(result, (ToolResult, ToolReplayResult, InFlightInvocationError))
        for result in same_results
    )
    with database.connection() as connection:
        assert TaskRepository(connection).get("task-audit")["revision"] == 1
        assert (
            connection.execute("SELECT count(*) FROM state_mutations").fetchone()[0]
            == 1
        )
        replay = asyncio.run(
            _executor(connection).execute_step(
                invocation_id="concurrent-restart",
                idempotency_key="concurrent-key",
                tool_name="complete_study_task",
                arguments=_COMPLETE_ARGUMENTS,
                context=_context(),
            )
        )
        assert isinstance(replay, ToolReplayResult)

    different_database = Database(tmp_path / "audit-concurrent-different.sqlite3")
    different_database.migrate()
    with different_database.connection() as connection:
        _setup_state(connection)

    def run_different(
        invocation_id: str, completed_at: str, barrier: threading.Barrier
    ):
        with different_database.connection() as connection:
            barrier.wait(timeout=2)
            try:
                return asyncio.run(
                    _executor(connection).execute_step(
                        invocation_id=invocation_id,
                        idempotency_key="concurrent-different-key",
                        tool_name="complete_study_task",
                        arguments={**_COMPLETE_ARGUMENTS, "completed_at": completed_at},
                        context=_context(),
                    )
                )
            except Exception as error:
                return error

    different_payload_barrier = threading.Barrier(2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        different_results = list(
            pool.map(
                lambda pair: run_different(*pair, different_payload_barrier),
                (
                    ("different-a", "2026-07-16T12:00:00+00:00"),
                    ("different-b", "2026-07-16T13:00:00+00:00"),
                ),
            )
        )
    assert sum(isinstance(result, ToolResult) for result in different_results) == 1
    assert sum(isinstance(result, ValueError) for result in different_results) == 1
    with different_database.connection() as connection:
        assert TaskRepository(connection).get("task-audit")["revision"] == 1
        assert (
            connection.execute("SELECT count(*) FROM state_mutations").fetchone()[0]
            == 1
        )


class _BlockingArguments(ToolArguments):
    note_id: str


class _BlockingWriteTool:
    name = "blocking_note"
    permission_level = PermissionLevel.LOCAL_REVERSIBLE
    effect = ToolEffect.LOCAL_WRITE
    arguments_model = _BlockingArguments

    def __init__(self, started: asyncio.Event) -> None:
        self.started = started

    async def execute(
        self, arguments: _BlockingArguments, context: ToolContext
    ) -> ToolResult:
        assert isinstance(context.transaction, SQLiteToolSession)
        context.transaction.execute(
            "UPDATE study_tasks SET title = ? WHERE id = 'task-audit'",
            (arguments.note_id,),
        )
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def test_cancelled_level_two_rolls_back_domain_write_and_success_audit(tmp_path):
    async def exercise(connection: sqlite3.Connection) -> None:
        started = asyncio.Event()
        cancellation = asyncio.Event()
        registry = ToolRegistry()
        registry.register(_BlockingWriteTool(started))
        sink = SQLiteAuditSink(connection)
        task = asyncio.create_task(
            AgentStepExecutor(
                registry, sink, transaction_factory=sink.transaction
            ).execute_step(
                invocation_id="invocation-cancel",
                idempotency_key="cancel-key",
                tool_name="blocking_note",
                arguments={"note_id": "note-1"},
                context=ToolContext(
                    run_id="run-audit",
                    step_id="step-tool",
                    cancellation_event=cancellation,
                ),
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        cancellation.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)

    database = Database(tmp_path / "audit-cancel.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        asyncio.run(exercise(connection))
        assert TaskRepository(connection).get("task-audit")["title"] == "Review limits"
        invocation = AgentRepository(connection).get_tool_invocation(
            "invocation-cancel"
        )
        assert invocation["status"] == "cancelled"
        assert (
            connection.execute("SELECT count(*) FROM state_mutations").fetchone()[0]
            == 0
        )


class _TransactionControlTool(CompleteStudyTaskTool):
    def __init__(self, action: str) -> None:
        self.name = f"attempt_{action}"
        self.action = action

    async def execute(self, arguments, context):
        result = await super().execute(arguments, context)
        assert isinstance(context.transaction, SQLiteToolSession)
        getattr(context.transaction, self.action)()
        return result


@pytest.mark.parametrize("action", ["commit", "rollback"])
def test_level_two_tool_cannot_end_coordinated_transaction(action, tmp_path):
    database = Database(tmp_path / f"audit-tool-{action}.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        registry = ToolRegistry()
        tool = _TransactionControlTool(action)
        registry.register(tool)
        sink = SQLiteAuditSink(connection)

        with pytest.raises(PermissionError, match=f"cannot {action}"):
            asyncio.run(
                AgentStepExecutor(
                    registry, sink, transaction_factory=sink.transaction
                ).execute_step(
                    invocation_id=f"invocation-attempt-{action}",
                    idempotency_key=f"attempt-{action}",
                    tool_name=tool.name,
                    arguments=_COMPLETE_ARGUMENTS,
                    context=_context(),
                )
            )

        task = TaskRepository(connection).get("task-audit")
        assert task["status"] == "upcoming"
        assert task["revision"] == 0
        invocation = AgentRepository(connection).get_tool_invocation(
            f"invocation-attempt-{action}"
        )
        assert invocation["status"] == "failed"
        assert invocation["error_code"] == "PermissionError"
        assert (
            connection.execute("SELECT count(*) FROM state_mutations").fetchone()[0]
            == 0
        )


class _CursorConnectionEscapeTool(CompleteStudyTaskTool):
    name = "attempt_cursor_connection_escape"

    async def execute(self, arguments, context):
        result = await super().execute(arguments, context)
        assert isinstance(context.transaction, SQLiteToolSession)
        cursor = context.transaction.execute(
            "SELECT * FROM study_tasks WHERE id = ?", (arguments.task_id,)
        )
        cursor.connection.commit()
        return result


def test_level_two_tool_cannot_escape_through_cursor_connection(tmp_path):
    database = Database(tmp_path / "audit-cursor-escape.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        registry = ToolRegistry()
        registry.register(_CursorConnectionEscapeTool())
        sink = SQLiteAuditSink(connection)

        with pytest.raises(AttributeError, match="connection"):
            asyncio.run(
                AgentStepExecutor(
                    registry, sink, transaction_factory=sink.transaction
                ).execute_step(
                    invocation_id="invocation-cursor-escape",
                    idempotency_key="cursor-escape",
                    tool_name="attempt_cursor_connection_escape",
                    arguments=_COMPLETE_ARGUMENTS,
                    context=_context(),
                )
            )

        task = TaskRepository(connection).get("task-audit")
        assert task["status"] == "upcoming"
        assert task["revision"] == 0
        invocation = AgentRepository(connection).get_tool_invocation(
            "invocation-cursor-escape"
        )
        assert invocation["status"] == "failed"
        assert invocation["error_code"] == "AttributeError"
        assert (
            connection.execute("SELECT count(*) FROM state_mutations").fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "statement",
    [
        "BEGIN IMMEDIATE",
        "SAVEPOINT malicious",
        "PRAGMA foreign_keys = OFF",
        "ATTACH DATABASE ':memory:' AS stolen",
    ],
)
def test_tool_session_rejects_transaction_and_connection_control_sql(
    statement, tmp_path
):
    async def exercise(connection):
        async with SQLiteAuditSink(connection).transaction() as transaction:
            with pytest.raises(PermissionError):
                transaction.execute(statement)

    database = Database(tmp_path / "audit-control-sql.sqlite3")
    database.migrate()
    with database.connection() as connection:
        asyncio.run(exercise(connection))


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT courses.title FROM study_tasks, courses",
        "SELECT title FROM study_tasks WHERE EXISTS (SELECT 1 FROM courses)",
        "WITH stolen AS (SELECT title FROM courses) SELECT * FROM stolen",
        "SELECT main.courses.title FROM main.courses",
    ],
)
def test_tool_session_authorizer_blocks_other_table_query_shapes(statement, tmp_path):
    async def exercise(connection):
        async with SQLiteAuditSink(connection).transaction() as transaction:
            with pytest.raises(PermissionError, match="unauthorized"):
                transaction.execute(statement)

    database = Database(tmp_path / "audit-query-shapes.sqlite3")
    database.migrate()
    with database.connection() as connection:
        asyncio.run(exercise(connection))


class _FailAfterPersistSink(SQLiteAuditSink):
    async def record_succeeded(self, record, *, mutations, transaction) -> None:
        await super().record_succeeded(
            record,
            mutations=mutations,
            transaction=transaction,
        )
        raise RuntimeError("audit storage failed before commit")


def test_sqlite_success_audit_failure_rolls_back_domain_and_mutation_rows(tmp_path):
    database = Database(tmp_path / "audit-failure.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        registry = ToolRegistry()
        registry.register(CompleteStudyTaskTool())
        sink = _FailAfterPersistSink(connection)
        with pytest.raises(RuntimeError, match="audit storage failed"):
            asyncio.run(
                AgentStepExecutor(
                    registry, sink, transaction_factory=sink.transaction
                ).execute_step(
                    invocation_id="invocation-failed-audit",
                    idempotency_key="failed-audit",
                    tool_name="complete_study_task",
                    arguments=_COMPLETE_ARGUMENTS,
                    context=_context(),
                )
            )
        task = TaskRepository(connection).get("task-audit")
        assert task["status"] == "upcoming"
        assert task["revision"] == 0
        assert (
            AgentRepository(connection).get_tool_invocation("invocation-failed-audit")[
                "status"
            ]
            == "failed"
        )
        assert (
            connection.execute("SELECT count(*) FROM state_mutations").fetchone()[0]
            == 0
        )


def test_study_task_undo_is_audited_replayable_and_safely_redoable(tmp_path):
    database = Database(tmp_path / "audit-undo.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _setup_state(connection)
        complete = asyncio.run(
            _executor(connection).execute_step(
                invocation_id="invocation-complete",
                idempotency_key="complete-once",
                tool_name="complete_study_task",
                arguments=_COMPLETE_ARGUMENTS,
                context=_context(),
            )
        )
        assert isinstance(complete, ToolResult)
        repository = AgentRepository(connection)
        original = repository.list_state_mutations("invocation-complete")[0]
        sink = SQLiteAuditSink(connection)
        undo = UndoExecutor(sink, default_undo_registry())
        result = asyncio.run(
            undo.execute(
                run_id="run-audit",
                step_id="step-undo",
                mutation_id=original["id"],
                invocation_id="invocation-undo",
                idempotency_key="undo-once",
                cancellation_event=asyncio.Event(),
            )
        )
        assert isinstance(result, ToolResult)
        restored = TaskRepository(connection).get("task-audit")
        assert restored["status"] == "upcoming"
        assert restored["revision"] == 2
        assert restored["updated_at"] != original["before"]["updated_at"]
        with pytest.raises(ValueError, match="updated concurrently"):
            TaskRepository(connection).complete(
                "task-audit",
                expected_revision=0,
                completed_at="2026-07-16T14:00:00+00:00",
            )

        replay = asyncio.run(
            undo.execute(
                run_id="run-audit",
                step_id="step-undo",
                mutation_id=original["id"],
                invocation_id="invocation-undo-replay",
                idempotency_key="undo-once",
                cancellation_event=asyncio.Event(),
            )
        )
        assert isinstance(replay, ToolReplayResult)
        assert TaskRepository(connection).get("task-audit")["revision"] == 2

        inverse = repository.list_state_mutations("invocation-undo")[0]
        redone = asyncio.run(
            undo.execute(
                run_id="run-audit",
                step_id="step-redo",
                mutation_id=inverse["id"],
                invocation_id="invocation-redo",
                idempotency_key="redo-once",
                cancellation_event=asyncio.Event(),
            )
        )
        assert isinstance(redone, ToolResult)
        current = TaskRepository(connection).get("task-audit")
        assert current["status"] == "completed"
        assert current["revision"] == 3
        assert repository.get_state_mutation(original["id"])["undone_at"] is not None
        assert repository.get_state_mutation(inverse["id"])["undone_at"] is not None
