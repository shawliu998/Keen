from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping

import pytest
from pydantic import ValidationError

from app.agent.event_stream import AgentEventStore, DurableEventStream, encode_sse
from app.agent.executor import AgentStepExecutor
import app.agent.orchestrator as orchestrator_module
from app.agent.orchestrator import AgentOrchestrator
from app.agent.provider import (
    ContentDelta,
    FixedAutomationProvider,
    ProviderCheckpoint,
    ProviderFinished,
    ProviderRequest,
    ProviderWarning,
    ToolCall,
)
from app.agent.types import StateMutation, ToolContext, ToolResult
from app.agent.sqlite_audit import SQLiteAuditSink
from app.agent.registry import ToolRegistry
from app.agent.types import (
    PermissionLevel,
    ToolArguments,
    ToolEffect,
    ToolReplayResult,
)
from app.database import Database
from app.repositories.agent_repository import AgentRepository


class _Executor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    async def execute_step(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
        context: ToolContext,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        context.raise_if_cancelled()
        assert idempotency_key is not None
        self.calls.append((invocation_id, tool_name, arguments))
        note_id = str(arguments["note_id"])
        return ToolResult(
            output={"entity_id": note_id, "body": "private note body"},
            mutations=(
                StateMutation(
                    entity_type="note",
                    entity_id=note_id,
                    operation="create",
                    before=None,
                    after={"title": "Limits"},
                    undo={
                        "operation": "delete",
                        "entity_type": "note",
                        "entity_id": note_id,
                    },
                ),
            ),
        )


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "orchestrator.sqlite3")
    database.migrate()
    return database


def _create_run(database: Database, *, run_id: str = "run-1") -> None:
    with database.connection() as connection:
        AgentRepository(connection).create_run(
            run_id=run_id,
            kind="conversation",
            user_intent="Explain limits",
            mode="teach",
            provider="automation",
            model="fixed-actions",
            prompt_version="v1",
            input_data={"question": "What is a limit?"},
            idempotency_key=run_id,
        )


def test_orchestrator_persists_ordered_public_events_and_terminal_state(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    provider = FixedAutomationProvider(
        [
            ProviderWarning(code="fixture_notice", message="Automation only"),
            ToolCall(
                call_id="call-1",
                tool_name="create_note",
                arguments={"note_id": "note-1"},
            ),
            ContentDelta(text="A limit describes nearby behavior."),
            ProviderCheckpoint(label="explanation_ready", data={"unit_id": "u-1"}),
            ProviderFinished(),
        ]
    )
    executor = _Executor()
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(event_store=store, provider=provider, executor=executor).run(
            "run-1"
        )
    )

    events = store.list_events("run-1")
    assert [event.sequence for event in events] == list(range(len(events)))
    assert [event.event_type for event in events] == [
        "metadata",
        "status",
        "warning",
        "tool_start",
        "tool_result",
        "state_mutation",
        "content_delta",
        "checkpoint",
        "status",
        "done",
    ]
    assert events[4].payload["result"] == {
        "body": "[REDACTED]",
        "entity_id": "note-1",
    }
    assert "before" not in events[5].payload
    assert "after" not in events[5].payload
    assert "undo" not in events[5].payload
    assert store.get_run("run-1")["status"] == "completed"
    assert len(executor.calls) == 1
    assert executor.calls[0][1:] == ("create_note", {"note_id": "note-1"})
    assert executor.calls[0][0].startswith("inv-")
    with database.connection() as connection:
        step = connection.execute(
            "SELECT status, kind FROM agent_steps WHERE run_id = 'run-1'"
        ).fetchone()
    assert tuple(step) == ("completed", "tool")
    assert provider.closed is True
    assert encode_sse(events[-1]).startswith(
        f"id: {events[-1].id}\nevent: done\ndata: "
    )


def test_last_event_id_replays_strictly_after_cursor_without_duplicates(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    store = AgentEventStore(database)
    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=FixedAutomationProvider(
                [ContentDelta(text="one"), ContentDelta(text="two"), ProviderFinished()]
            ),
            executor=_Executor(),
        ).run("run-1")
    )
    all_events = store.list_events("run-1")
    cursor = all_events[2]

    async def replay_after_cursor():
        return [
            event
            async for event in DurableEventStream(store).replay(
                "run-1", last_event_id=cursor.id
            )
        ]

    replayed = asyncio.run(replay_after_cursor())
    assert [event.id for event in replayed] == [
        event.id for event in all_events if event.sequence > cursor.sequence
    ]
    assert cursor.id not in {event.id for event in replayed}
    with pytest.raises(LookupError, match="Last-Event-ID"):
        store.sequence_after_last_event_id("run-1", "missing-event")


class _ReplayExecutor:
    async def execute_step(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
        context: ToolContext,
        idempotency_key: str | None = None,
    ) -> ToolReplayResult:
        del tool_name, arguments, context, idempotency_key
        return ToolReplayResult(
            invocation_id=invocation_id,
            result_summary={"entity_id": "note-1"},
            mutation_ids=("mutation-1",),
        )


def test_replayed_tool_result_is_emitted_without_assuming_raw_output(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    store = AgentEventStore(database)
    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=FixedAutomationProvider(
                [
                    ToolCall(
                        call_id="call-1",
                        tool_name="create_note",
                        arguments={"note_id": "note-1"},
                    ),
                    ProviderFinished(),
                ]
            ),
            executor=_ReplayExecutor(),
        ).run("run-1")
    )
    events = store.list_events("run-1")
    tool_result = next(event for event in events if event.event_type == "tool_result")
    mutation = next(event for event in events if event.event_type == "state_mutation")
    assert tool_result.payload["replayed"] is True
    assert mutation.payload == {
        "callId": "call-1",
        "invocationId": tool_result.payload["invocationId"],
        "mutationId": "mutation-1",
        "replayed": True,
    }


class _ReadArguments(ToolArguments):
    concept_id: str


class _ReadTool:
    name = "read_concept"
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = _ReadArguments

    async def execute(
        self, arguments: _ReadArguments, context: ToolContext
    ) -> ToolResult:
        context.raise_if_cancelled()
        return ToolResult(output={"concept_id": arguments.concept_id})


def test_real_sqlite_audit_sink_accepts_persisted_tool_step_foreign_key(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    registry = ToolRegistry()
    registry.register(_ReadTool())
    with database.connection() as audit_connection:
        sink = SQLiteAuditSink(audit_connection)
        asyncio.run(
            AgentOrchestrator(
                event_store=AgentEventStore(database),
                provider=FixedAutomationProvider(
                    [
                        ToolCall(
                            call_id="read-1",
                            tool_name="read_concept",
                            arguments={"concept_id": "concept-limits"},
                        ),
                        ProviderFinished(),
                    ]
                ),
                executor=AgentStepExecutor(registry, sink),
            ).run("run-1")
        )
        invocation = audit_connection.execute(
            "SELECT status, step_id, idempotency_key FROM tool_invocations"
        ).fetchone()
    assert invocation["status"] == "succeeded"
    assert invocation["step_id"].startswith("step-")
    assert invocation["idempotency_key"].startswith("tool-")


class _BlockingProvider:
    name = "automation"
    model = "blocking"
    version = "v1"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ContentDelta]:
        del request
        self.started.set()
        await asyncio.Event().wait()
        yield ContentDelta(text="unreachable")

    async def aclose(self) -> None:
        self.closed = True


class _BlockingExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute_step(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
        context: ToolContext,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        del invocation_id, tool_name, arguments, idempotency_key
        self.started.set()
        await context.cancellation_event.wait()
        context.raise_if_cancelled()
        raise AssertionError("unreachable")


class _CommittedThenCancelledExecutor:
    """Simulate cancellation arriving immediately after a durable tool commit."""

    async def execute_step(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
        context: ToolContext,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        del invocation_id, tool_name, arguments, idempotency_key
        context.cancellation_event.set()
        return ToolResult(
            output={"entity_id": "note-1"},
            mutations=(
                StateMutation(
                    entity_type="note",
                    entity_id="note-1",
                    operation="create",
                    before=None,
                    after={"title": "Limits"},
                    undo={
                        "operation": "delete",
                        "entity_type": "note",
                        "entity_id": "note-1",
                    },
                ),
            ),
        )


def test_cancel_propagates_to_provider_and_never_writes_false_done(tmp_path):
    async def exercise(database: Database) -> tuple[_BlockingProvider, AgentEventStore]:
        store = AgentEventStore(database)
        provider = _BlockingProvider()
        orchestrator = AgentOrchestrator(
            event_store=store, provider=provider, executor=_Executor()
        )
        execution = asyncio.create_task(orchestrator.run("run-1"))
        await provider.started.wait()
        assert await orchestrator.cancel("run-1") is True
        with pytest.raises(asyncio.CancelledError):
            await execution
        return provider, store

    database = _database(tmp_path)
    _create_run(database)
    provider, store = asyncio.run(exercise(database))
    events = store.list_events("run-1")
    assert store.get_run("run-1")["status"] == "cancelled"
    assert [event.event_type for event in events][-2:] == ["status", "error"]
    assert events[-1].payload["code"] == "cancelled"
    assert not any(event.event_type == "done" for event in events)
    assert provider.closed is True


def test_cancel_during_tool_marks_real_step_cancelled(tmp_path):
    async def exercise(database: Database) -> AgentEventStore:
        store = AgentEventStore(database)
        executor = _BlockingExecutor()
        orchestrator = AgentOrchestrator(
            event_store=store,
            provider=FixedAutomationProvider(
                [
                    ToolCall(
                        call_id="call-1",
                        tool_name="blocking_tool",
                        arguments={},
                    ),
                    ProviderFinished(),
                ]
            ),
            executor=executor,
        )
        execution = asyncio.create_task(orchestrator.run("run-1"))
        await executor.started.wait()
        assert await orchestrator.cancel("run-1") is True
        with pytest.raises(asyncio.CancelledError):
            await execution
        return store

    database = _database(tmp_path)
    _create_run(database)
    store = asyncio.run(exercise(database))
    with database.connection() as connection:
        step = connection.execute(
            "SELECT status, error_code, output_json FROM agent_steps"
        ).fetchone()
    assert tuple(step) == ("cancelled", "cancelled", None)
    assert store.get_run("run-1")["status"] == "cancelled"
    assert not any(
        event.event_type in {"tool_result", "done"}
        for event in store.list_events("run-1")
    )


def test_cancel_after_tool_commit_preserves_success_and_mutation_events(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    store = AgentEventStore(database)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            AgentOrchestrator(
                event_store=store,
                provider=FixedAutomationProvider(
                    [
                        ToolCall(
                            call_id="call-1",
                            tool_name="create_note",
                            arguments={"note_id": "note-1"},
                        ),
                        ProviderFinished(),
                    ]
                ),
                executor=_CommittedThenCancelledExecutor(),
            ).run("run-1")
        )
    events = store.list_events("run-1")
    event_types = [event.event_type for event in events]
    assert "tool_result" in event_types
    assert "state_mutation" in event_types
    assert event_types[-2:] == ["status", "error"]
    assert not any(event.event_type == "done" for event in events)
    with database.connection() as connection:
        step = connection.execute(
            "SELECT status, output_json FROM agent_steps"
        ).fetchone()
    assert step["status"] == "completed"
    assert step["output_json"] is not None


def test_single_agent_rejects_a_second_concurrent_run(tmp_path):
    async def exercise(database: Database) -> None:
        provider = _BlockingProvider()
        orchestrator = AgentOrchestrator(
            event_store=AgentEventStore(database),
            provider=provider,
            executor=_Executor(),
        )
        first = asyncio.create_task(orchestrator.run("run-1"))
        await provider.started.wait()
        with pytest.raises(RuntimeError, match="single-Agent"):
            await orchestrator.run("run-2")
        assert await orchestrator.cancel("run-1") is True
        with pytest.raises(asyncio.CancelledError):
            await first

    database = _database(tmp_path)
    _create_run(database, run_id="run-1")
    _create_run(database, run_id="run-2")
    asyncio.run(exercise(database))
    assert AgentEventStore(database).get_run("run-2")["status"] == "queued"


class _FailingProvider:
    name = "automation"
    model = "failure"
    version = "v1"

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ContentDelta]:
        del request
        yield ContentDelta(text="partial")
        raise RuntimeError("secret provider response")

    async def aclose(self) -> None:
        pass


@pytest.mark.parametrize("failure", ["exception", "disconnect"])
def test_provider_failure_or_disconnect_is_persisted_as_failed(tmp_path, failure):
    database = _database(tmp_path)
    _create_run(database)
    provider = (
        _FailingProvider()
        if failure == "exception"
        else FixedAutomationProvider([ContentDelta(text="partial")])
    )
    store = AgentEventStore(database)
    asyncio.run(
        AgentOrchestrator(
            event_store=store, provider=provider, executor=_Executor()
        ).run("run-1")
    )
    events = store.list_events("run-1")
    run = store.get_run("run-1")
    assert run["status"] == "failed"
    assert [event.event_type for event in events][-2:] == ["status", "error"]
    assert not any(event.event_type == "done" for event in events)
    if failure == "exception":
        assert run["error_code"] == "runtime_error"
        assert "secret provider response" not in run["error_detail"]
    else:
        assert run["error_code"] == "provider_disconnected"


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "actions"),
    [
        (
            "_MAX_CONTENT_BYTES",
            3,
            [ContentDelta(text="four"), ProviderFinished()],
        ),
        (
            "_MAX_PROVIDER_ACTIONS",
            1,
            [ContentDelta(text="one"), ProviderFinished()],
        ),
        (
            "_MAX_PROVIDER_BYTES",
            32,
            [
                ProviderCheckpoint(
                    label="oversize_checkpoint", data={"unit_id": "unit-1"}
                ),
                ProviderFinished(),
            ],
        ),
    ],
)
def test_provider_stream_limits_fail_without_unbounded_events(
    tmp_path, monkeypatch, limit_name, limit_value, actions
):
    monkeypatch.setattr(orchestrator_module, limit_name, limit_value)
    database = _database(tmp_path)
    _create_run(database)
    store = AgentEventStore(database)
    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=FixedAutomationProvider(actions),
            executor=_Executor(),
        ).run("run-1")
    )
    run = store.get_run("run-1")
    assert run["status"] == "failed"
    assert run["error_code"] == "provider_limit_error"
    assert len(store.list_events("run-1")) <= 5
    assert not any(event.event_type == "done" for event in store.list_events("run-1"))


def test_invalid_stored_provider_request_transitions_from_running_to_failed(tmp_path):
    database = _database(tmp_path)
    with database.connection() as connection:
        AgentRepository(connection).create_run(
            run_id="run-1",
            kind="conversation",
            user_intent="Explain limits",
            mode="teach",
            provider="automation",
            model="fixed-actions",
            prompt_version="v1",
            input_data={"chainOfThought": "must not be retained by provider request"},
            idempotency_key="run-1",
        )
    store = AgentEventStore(database)
    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=FixedAutomationProvider([ProviderFinished()]),
            executor=_Executor(),
        ).run("run-1")
    )
    assert store.get_run("run-1")["status"] == "failed"
    assert [event.event_type for event in store.list_events("run-1")] == [
        "metadata",
        "status",
        "status",
        "error",
    ]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ProviderRequest(
            run_id="run-1",
            user_intent="teach",
            mode="teach",
            input={"chainOfThought": "private"},
        ),
        lambda: ToolCall(
            call_id="call-1",
            tool_name="search_sources",
            arguments={"scratch-pad": "private"},
        ),
        lambda: ProviderCheckpoint(
            label="unsafe", data={"nested": {"reasoningTrace": "private"}}
        ),
    ],
)
def test_provider_contract_rejects_hidden_reasoning(factory):
    with pytest.raises(ValidationError, match="hidden reasoning"):
        factory()
