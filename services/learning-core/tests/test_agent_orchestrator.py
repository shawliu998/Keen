from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.agent.event_stream import AgentEventStore, DurableEventStream, encode_sse
from app.agent.executor import AgentStepExecutor, RecoverableReadToolError
import app.agent.orchestrator as orchestrator_module
from app.agent.orchestrator import AgentOrchestrator, ProviderToolRuntime
from app.agent.provider import (
    ContentDelta,
    FixedAutomationProvider,
    ProviderCheckpoint,
    ProviderFinished,
    ProviderRequest,
    ProviderToolError,
    ProviderToolFeedback,
    ProviderToolResult,
    ProviderWarning,
    ToolCall,
)
from app.agent.types import StateMutation, ToolContext, ToolOutput, ToolResult
from app.agent.sqlite_audit import SQLiteAuditSink
from app.agent.tools.product import register_initial_product_tools
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


class _CreateNoteArguments(ToolArguments):
    note_id: str


class _CreateNoteOutput(ToolOutput):
    entity_id: str
    body: str


class _CreateNoteReadTool:
    name = "create_note"
    description = "Read a deterministic local test note."
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = _CreateNoteArguments
    result_model = _CreateNoteOutput

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(
        self, arguments: _CreateNoteArguments, context: ToolContext
    ) -> ToolResult:
        context.raise_if_cancelled()
        self.calls.append(arguments.note_id)
        return ToolResult(
            output={
                "entity_id": arguments.note_id,
                "body": "private note body",
            }
        )


class _NoopAuditSink:
    async def record_started(self, record):
        del record

    async def record_succeeded(self, record, *, mutations, transaction):
        del record, mutations, transaction

    async def record_rejected(self, record):
        del record

    async def record_failed(self, record):
        del record

    async def record_cancelled(self, record):
        del record


class _FailingTerminalAuditSink(_NoopAuditSink):
    async def record_failed(self, record):
        del record
        raise RuntimeError("audit storage unavailable")


class _RecoveryProvider:
    name = "recovery-test"
    model = "recovery-driven"
    version = "v1"

    def __init__(self, first_arguments: Mapping[str, object]) -> None:
        self._first_arguments = first_arguments
        self.feedback: list[ProviderToolFeedback] = []
        self._feedback: asyncio.Queue[ProviderToolFeedback] = asyncio.Queue()
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        del request
        yield ToolCall(
            call_id="call-recovery-first",
            tool_name="create_note",
            arguments=dict(self._first_arguments),
        )
        first = await self._feedback.get()
        assert isinstance(first, ProviderToolError)
        yield ToolCall(
            call_id="call-recovery-corrected",
            tool_name="create_note",
            arguments={"note_id": "note-recovered"},
        )
        second = await self._feedback.get()
        assert isinstance(second, ProviderToolResult)
        yield ContentDelta(text="Recovered with a corrected read-only tool call.")
        yield ProviderFinished()

    async def submit_tool_result(self, result: ProviderToolFeedback) -> None:
        self.feedback.append(result)
        await self._feedback.put(result)

    async def aclose(self) -> None:
        self.closed = True


class _TemporaryReadTool(_CreateNoteReadTool):
    async def execute(
        self, arguments: _CreateNoteArguments, context: ToolContext
    ) -> ToolResult:
        if not self.calls:
            self.calls.append(arguments.note_id)
            raise RecoverableReadToolError(
                "temporary local read failure at /private/course.sqlite"
            )
        return await super().execute(arguments, context)


class _InternalValidationFailureTool(_CreateNoteReadTool):
    async def execute(
        self, arguments: _CreateNoteArguments, context: ToolContext
    ) -> ToolResult:
        del arguments, context
        return ToolResult(output={"body": "x" * 65_537})


def _temporary_read_runtime() -> tuple[ProviderToolRuntime, _TemporaryReadTool]:
    registry = ToolRegistry()
    tool = _TemporaryReadTool()
    registry.register(tool)
    executor = AgentStepExecutor(registry, _NoopAuditSink())
    return ProviderToolRuntime.from_readonly_registry(registry, executor), tool


def _temporary_read_runtime_with_audit(
    audit_sink,
) -> tuple[ProviderToolRuntime, _TemporaryReadTool]:
    registry = ToolRegistry()
    tool = _TemporaryReadTool()
    registry.register(tool)
    executor = AgentStepExecutor(registry, audit_sink)
    return ProviderToolRuntime.from_readonly_registry(registry, executor), tool


def _internal_validation_failure_runtime() -> tuple[
    ProviderToolRuntime, _InternalValidationFailureTool
]:
    registry = ToolRegistry()
    tool = _InternalValidationFailureTool()
    registry.register(tool)
    executor = AgentStepExecutor(registry, _NoopAuditSink())
    return ProviderToolRuntime.from_readonly_registry(registry, executor), tool


class _RepeatedInvalidProvider:
    name = "repeated-invalid"
    model = "repeated-invalid"
    version = "v1"

    def __init__(self, count: int, *, repeat_same: bool = False) -> None:
        self.count = count
        self.repeat_same = repeat_same
        self.feedback: list[ProviderToolFeedback] = []
        self._feedback: asyncio.Queue[ProviderToolFeedback] = asyncio.Queue()
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        del request
        for index in range(self.count):
            yield ToolCall(
                call_id=f"call-invalid-{index}",
                tool_name="create_note",
                arguments={"note_id": 0 if self.repeat_same else index},
            )
            await self._feedback.get()
        yield ProviderFinished()

    async def submit_tool_result(self, result: ProviderToolFeedback) -> None:
        self.feedback.append(result)
        await self._feedback.put(result)

    async def aclose(self) -> None:
        self.closed = True


def _create_note_runtime() -> tuple[ProviderToolRuntime, _CreateNoteReadTool]:
    registry = ToolRegistry()
    tool = _CreateNoteReadTool()
    registry.register(tool)
    executor = AgentStepExecutor(registry, _NoopAuditSink())
    return ProviderToolRuntime.from_readonly_registry(registry, executor), tool


class _FeedbackDrivenProvider:
    name = "feedback-test"
    model = "feedback-driven"
    version = "v1"

    def __init__(self) -> None:
        self.feedback: list[ProviderToolResult] = []
        self.feedback_received = asyncio.Event()
        self.request: ProviderRequest | None = None
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        self.request = request
        yield ToolCall(
            call_id="call-feedback-1",
            tool_name="create_note",
            arguments={"note_id": "note-feedback-1"},
        )
        await self.feedback_received.wait()
        result = self.feedback[0]
        assert result.output["body"] == "private note body"
        yield ContentDelta(text=f"Created {result.output['entity_id']}.")
        yield ProviderFinished()

    async def submit_tool_result(self, result: ProviderToolResult) -> None:
        self.feedback.append(result)
        self.feedback_received.set()

    async def aclose(self) -> None:
        self.closed = True


class _TwoRoundFeedbackProvider(_FeedbackDrivenProvider):
    def __init__(self) -> None:
        super().__init__()
        self.second_feedback_received = asyncio.Event()

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        del request
        yield ToolCall(
            call_id="call-round-1",
            tool_name="create_note",
            arguments={"note_id": "note-round-1"},
        )
        await self.feedback_received.wait()
        assert self.feedback[0].output["entity_id"] == "note-round-1"
        yield ToolCall(
            call_id="call-round-2",
            tool_name="create_note",
            arguments={"note_id": "note-round-2"},
        )
        await self.second_feedback_received.wait()
        assert self.feedback[1].output["entity_id"] == "note-round-2"
        yield ContentDelta(text="Created both notes from real tool results.")
        yield ProviderFinished()

    async def submit_tool_result(self, result: ProviderToolResult) -> None:
        self.feedback.append(result)
        if len(self.feedback) == 1:
            self.feedback_received.set()
        elif len(self.feedback) == 2:
            self.second_feedback_received.set()


class _NoFeedbackProvider:
    name = "no-feedback"
    model = "invalid-tool-provider"
    version = "v1"

    def __init__(self) -> None:
        self.closed = False

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        del request
        yield ToolCall(
            call_id="call-without-feedback",
            tool_name="create_note",
            arguments={"note_id": "must-not-execute"},
        )
        yield ProviderFinished()

    async def aclose(self) -> None:
        self.closed = True


class _CancellationResistantFeedbackProvider(_FeedbackDrivenProvider):
    def __init__(self, *, raises_after_cancel: bool) -> None:
        super().__init__()
        self.submit_started = asyncio.Event()
        self.release = asyncio.Event()
        self.raises_after_cancel = raises_after_cancel

    async def stream(self, request: ProviderRequest) -> AsyncIterator:
        del request
        yield ToolCall(
            call_id="call-cancel-feedback",
            tool_name="create_note",
            arguments={"note_id": "note-cancel-feedback"},
        )
        yield ProviderFinished()

    async def submit_tool_result(self, result: ProviderToolResult) -> None:
        self.feedback.append(result)
        self.submit_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if self.raises_after_cancel:
                raise RuntimeError("private provider cancel failure")
            await self.release.wait()


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


def test_validation_failure_is_redacted_then_provider_corrects_read_call(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    runtime, tool = _create_note_runtime()
    provider = _RecoveryProvider({"note_id": 7})
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store, provider=provider, tool_runtime=runtime
        ).run("run-1")
    )

    assert store.get_run("run-1")["status"] == "completed"
    assert tool.calls == ["note-recovered"]
    assert isinstance(provider.feedback[0], ProviderToolError)
    assert provider.feedback[0].model_dump(mode="json") == {
        "call_id": "call-recovery-first",
        "tool_name": "create_note",
        "invocation_id": provider.feedback[0].invocation_id,
        "trust": "untrusted_tool_data",
        "kind": "tool_error",
        "code": "invalid_arguments",
        "category": "validation",
        "retryable": True,
        "recovery_action": "correct_arguments",
    }
    events = store.list_events("run-1")
    failed = next(event for event in events if event.event_type == "tool_result")
    assert failed.payload == {
        "callId": "call-recovery-first",
        "invocationId": provider.feedback[0].invocation_id,
        "toolName": "create_note",
        "failed": True,
        "code": "invalid_arguments",
        "retryable": True,
        "replayed": False,
    }
    assert "note_id" not in str(failed.payload)


def test_temporary_read_failure_is_redacted_then_provider_corrects_call(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    runtime, tool = _temporary_read_runtime()
    provider = _RecoveryProvider({"note_id": "note-temporary"})
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store, provider=provider, tool_runtime=runtime
        ).run("run-1")
    )

    assert store.get_run("run-1")["status"] == "completed"
    assert tool.calls == ["note-temporary", "note-recovered"]
    assert isinstance(provider.feedback[0], ProviderToolError)
    assert provider.feedback[0].code == "temporary_read_failure"
    public_payloads = [
        event.payload
        for event in store.list_events("run-1")
        if event.event_type == "tool_result"
    ]
    assert public_payloads[0]["code"] == "temporary_read_failure"
    assert "/private/course.sqlite" not in str(public_payloads)


def test_recoverable_error_budget_terminalizes_fifth_failed_step(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    runtime, tool = _create_note_runtime()
    provider = _RepeatedInvalidProvider(5)
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store, provider=provider, tool_runtime=runtime
        ).run("run-1")
    )

    assert store.get_run("run-1")["status"] == "failed"
    assert store.get_run("run-1")["error_code"] == "provider_limit_error"
    assert tool.calls == []
    assert len(provider.feedback) == 4
    with database.connection() as connection:
        steps = connection.execute(
            "SELECT status FROM agent_steps ORDER BY ordinal"
        ).fetchall()
    assert [row[0] for row in steps] == ["failed"] * 5
    assert (
        len(
            [
                event
                for event in store.list_events("run-1")
                if event.event_type == "tool_result"
            ]
        )
        == 5
    )


def test_repeated_recoverable_failure_is_publicly_failed_but_not_retried(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    runtime, _tool = _create_note_runtime()
    provider = _RepeatedInvalidProvider(2, repeat_same=True)
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store, provider=provider, tool_runtime=runtime
        ).run("run-1")
    )

    assert store.get_run("run-1")["error_code"] == "provider_protocol_error"
    assert len(provider.feedback) == 1
    assert (
        len(
            [
                event
                for event in store.list_events("run-1")
                if event.event_type == "tool_result"
            ]
        )
        == 2
    )
    with database.connection() as connection:
        statuses = connection.execute(
            "SELECT status FROM agent_steps ORDER BY ordinal"
        ).fetchall()
    assert [row[0] for row in statuses] == ["failed", "failed"]


def test_recoverable_read_failure_is_terminal_when_failure_audit_is_uncertain(
    tmp_path,
):
    database = _database(tmp_path)
    _create_run(database)
    runtime, _tool = _temporary_read_runtime_with_audit(_FailingTerminalAuditSink())
    provider = _RecoveryProvider({"note_id": "note-temporary"})
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store, provider=provider, tool_runtime=runtime
        ).run("run-1")
    )

    run = store.get_run("run-1")
    assert run["status"] == "failed"
    assert run["error_code"] == "tool_audit_uncertain_error"
    assert provider.feedback == []
    assert not any(
        event.event_type == "tool_result" for event in store.list_events("run-1")
    )


def test_internal_tool_validation_failure_is_not_recoverable_as_bad_arguments(
    tmp_path,
):
    database = _database(tmp_path)
    _create_run(database)
    runtime, _tool = _internal_validation_failure_runtime()
    provider = _RecoveryProvider({"note_id": "valid-provider-argument"})
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store, provider=provider, tool_runtime=runtime
        ).run("run-1")
    )

    run = store.get_run("run-1")
    assert run["status"] == "failed"
    assert run["error_code"] == "validation_error"
    assert provider.feedback == []
    assert not any(
        event.event_type == "tool_result" for event in store.list_events("run-1")
    )


def test_cancellation_after_durable_failed_result_prevents_private_feedback(
    tmp_path, monkeypatch
):
    database = _database(tmp_path)
    _create_run(database)
    runtime, _tool = _create_note_runtime()
    provider = _RecoveryProvider({"note_id": 7})
    store = AgentEventStore(database)
    orchestrator = AgentOrchestrator(
        event_store=store, provider=provider, tool_runtime=runtime
    )
    original_reserve = orchestrator_module._RecoverableToolErrorBudget.reserve

    def reserve_and_cancel(self, *, action, code):
        original_reserve(self, action=action, code=code)
        orchestrator._active["run-1"].set()

    monkeypatch.setattr(
        orchestrator_module._RecoverableToolErrorBudget,
        "reserve",
        reserve_and_cancel,
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(orchestrator.run("run-1"))

    assert store.get_run("run-1")["status"] == "cancelled"
    assert provider.feedback == []
    failed_results = [
        event
        for event in store.list_events("run-1")
        if event.event_type == "tool_result"
    ]
    assert len(failed_results) == 1
    assert failed_results[0].payload["failed"] is True


def test_failed_step_and_public_result_roll_back_together(tmp_path, monkeypatch):
    database = _database(tmp_path)
    _create_run(database)
    store = AgentEventStore(database)
    store.start_run(
        "run-1",
        metadata={
            "runId": "run-1",
            "provider": "test",
            "model": "test",
            "providerVersion": "test",
        },
    )
    store.start_tool_step(
        run_id="run-1",
        step_id="step-atomic-failure",
        ordinal=0,
        invocation_id="invocation-atomic-failure",
        tool_name="create_note",
        input_data={"toolName": "create_note", "callId": "call-atomic-failure"},
    )

    def reject_event(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("event storage unavailable")

    monkeypatch.setattr(store, "_append_event_once", reject_event)
    with pytest.raises(RuntimeError, match="event storage unavailable"):
        store.fail_tool_step_with_result(
            run_id="run-1",
            step_id="step-atomic-failure",
            error_code="invalid_arguments",
            result_payload={
                "callId": "call-atomic-failure",
                "invocationId": "invocation-atomic-failure",
                "toolName": "create_note",
                "failed": True,
                "code": "invalid_arguments",
                "retryable": True,
                "replayed": False,
            },
        )

    with database.connection() as connection:
        status = connection.execute(
            "SELECT status FROM agent_steps WHERE id = 'step-atomic-failure'"
        ).fetchone()[0]
    assert status == "running"
    assert not any(
        event.event_type == "tool_result" for event in store.list_events("run-1")
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


def test_real_tool_result_privately_drives_the_next_provider_turn(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    provider = _FeedbackDrivenProvider()
    store = AgentEventStore(database)
    runtime, tool = _create_note_runtime()

    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=provider,
            tool_runtime=runtime,
        ).run("run-1")
    )

    assert len(provider.feedback) == 1
    assert provider.request is not None
    assert [tool.name for tool in provider.request.tools] == ["create_note"]
    assert provider.request.tools[0].parameters["additionalProperties"] is False
    feedback = provider.feedback[0]
    assert feedback.call_id == "call-feedback-1"
    assert feedback.tool_name == "create_note"
    assert feedback.trust == "untrusted_tool_data"
    assert feedback.fidelity == "full"
    assert feedback.replayed is False
    assert feedback.output == {
        "entity_id": "note-feedback-1",
        "body": "private note body",
    }
    assert feedback.mutation_ids == ()
    assert tool.calls == ["note-feedback-1"]
    events = store.list_events("run-1")
    assert [event.event_type for event in events] == [
        "metadata",
        "status",
        "tool_start",
        "tool_result",
        "content_delta",
        "status",
        "done",
    ]
    assert events[3].payload["result"]["body"] == "[REDACTED]"
    serialized_events = "\n".join(encode_sse(event) for event in events)
    assert "private note body" not in serialized_events
    assert events[4].payload == {"delta": "Created note-feedback-1."}
    assert provider.closed is True


def test_two_sequential_tool_calls_receive_correlated_feedback_once(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    provider = _TwoRoundFeedbackProvider()
    store = AgentEventStore(database)
    runtime, tool = _create_note_runtime()

    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=provider,
            tool_runtime=runtime,
        ).run("run-1")
    )

    assert [feedback.call_id for feedback in provider.feedback] == [
        "call-round-1",
        "call-round-2",
    ]
    assert [feedback.output["entity_id"] for feedback in provider.feedback] == [
        "note-round-1",
        "note-round-2",
    ]
    assert tool.calls == ["note-round-1", "note-round-2"]
    events = store.list_events("run-1")
    assert [event.event_type for event in events].count("tool_result") == 2
    assert events[-1].event_type == "done"


def test_tool_call_without_feedback_capability_fails_before_execution(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    provider = _NoFeedbackProvider()
    executor = _Executor()
    store = AgentEventStore(database)
    runtime, tool = _create_note_runtime()

    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=provider,
            tool_runtime=runtime,
        ).run("run-1")
    )

    assert executor.calls == []
    assert tool.calls == []
    assert store.get_run("run-1")["status"] == "failed"
    assert store.get_run("run-1")["error_code"] == "provider_protocol_error"
    assert not any(
        event.event_type in {"tool_start", "tool_result", "done"}
        for event in store.list_events("run-1")
    )
    assert provider.closed is True


def test_nonfixture_provider_without_policy_is_deny_by_default(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    provider = _FeedbackDrivenProvider()
    executor = _Executor()
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=provider,
            executor=executor,
        ).run("run-1")
    )

    assert executor.calls == []
    assert provider.feedback == []
    assert store.get_run("run-1")["status"] == "failed"
    assert store.get_run("run-1")["error_code"] == "provider_protocol_error"
    assert not any(
        event.event_type in {"tool_start", "tool_result", "done"}
        for event in store.list_events("run-1")
    )


def test_executor_and_bound_runtime_cannot_be_combined(tmp_path):
    database = _database(tmp_path)
    runtime, _ = _create_note_runtime()

    with pytest.raises(ValueError, match="cannot be combined"):
        AgentOrchestrator(
            event_store=AgentEventStore(database),
            provider=_FeedbackDrivenProvider(),
            executor=_Executor(),
            tool_runtime=runtime,
        )


def test_orchestrator_rejects_provider_runtime_subclasses(tmp_path):
    database = _database(tmp_path)

    class _RuntimeSubclass(ProviderToolRuntime):
        @property
        def executor(self):
            return _Executor()

        @property
        def catalog(self):
            return ()

        @property
        def allowed_tool_names(self):
            return frozenset({"create_note"})

    forged = object.__new__(_RuntimeSubclass)
    with pytest.raises(ValueError, match="exact trusted type"):
        AgentOrchestrator(
            event_store=AgentEventStore(database),
            provider=_FeedbackDrivenProvider(),
            tool_runtime=forged,
        )


def test_tool_round_limit_is_cumulative_and_stops_before_next_execution(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(orchestrator_module, "_MAX_TOOL_ROUNDS", 1)
    database = _database(tmp_path)
    _create_run(database)
    provider = FixedAutomationProvider(
        [
            ToolCall(
                call_id="call-limit-1",
                tool_name="create_note",
                arguments={"note_id": "note-limit-1"},
            ),
            ToolCall(
                call_id="call-limit-2",
                tool_name="create_note",
                arguments={"note_id": "note-limit-2"},
            ),
            ProviderFinished(),
        ]
    )
    executor = _Executor()
    store = AgentEventStore(database)

    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=provider,
            executor=executor,
        ).run("run-1")
    )

    assert len(executor.calls) == 1
    assert len(provider.tool_results) == 1
    assert store.get_run("run-1")["status"] == "failed"
    assert store.get_run("run-1")["error_code"] == "provider_limit_error"
    assert not any(event.event_type == "done" for event in store.list_events("run-1"))


@pytest.mark.parametrize("raises_after_cancel", [False, True])
def test_cancel_during_feedback_is_bounded_and_remains_cancelled(
    tmp_path, monkeypatch, raises_after_cancel
):
    monkeypatch.setattr(
        orchestrator_module, "_PROVIDER_FEEDBACK_CANCEL_TIMEOUT_SECONDS", 0.01
    )

    async def exercise(database: Database) -> AgentEventStore:
        provider = _CancellationResistantFeedbackProvider(
            raises_after_cancel=raises_after_cancel
        )
        store = AgentEventStore(database)
        runtime, _ = _create_note_runtime()
        orchestrator = AgentOrchestrator(
            event_store=store,
            provider=provider,
            tool_runtime=runtime,
        )
        execution = asyncio.create_task(orchestrator.run("run-1"))
        await provider.submit_started.wait()
        assert await orchestrator.cancel("run-1") is True
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(execution, timeout=0.5)
        provider.release.set()
        await asyncio.sleep(0)
        return store

    database = _database(tmp_path)
    _create_run(database)
    store = asyncio.run(exercise(database))
    run = store.get_run("run-1")
    assert run["status"] == "cancelled"
    assert run["error_code"] == "cancelled"
    assert not any(event.event_type == "done" for event in store.list_events("run-1"))


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
    provider = FixedAutomationProvider(
        [
            ToolCall(
                call_id="call-1",
                tool_name="create_note",
                arguments={"note_id": "note-1"},
            ),
            ProviderFinished(),
        ]
    )
    asyncio.run(
        AgentOrchestrator(
            event_store=store,
            provider=provider,
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
    assert len(provider.tool_results) == 1
    feedback = provider.tool_results[0]
    assert feedback.replayed is True
    assert feedback.fidelity == "audit_summary"
    assert feedback.output == {"entity_id": "note-1"}


class _ReadArguments(ToolArguments):
    concept_id: str


class _ReadOutput(ToolOutput):
    concept_id: str


class _ReadTool:
    name = "read_concept"
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = _ReadArguments
    result_model = _ReadOutput

    async def execute(
        self, arguments: _ReadArguments, context: ToolContext
    ) -> ToolResult:
        context.raise_if_cancelled()
        return ToolResult(output={"concept_id": arguments.concept_id})


class _CountingReadTool(_ReadTool):
    def __init__(self) -> None:
        self.executions = 0

    async def execute(
        self, arguments: _ReadArguments, context: ToolContext
    ) -> ToolResult:
        self.executions += 1
        return await super().execute(arguments, context)


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


def test_same_provider_call_replays_private_audit_without_duplicate_public_result(
    tmp_path,
):
    database = _database(tmp_path)
    _create_run(database)
    registry = ToolRegistry()
    tool = _CountingReadTool()
    registry.register(tool)
    provider = FixedAutomationProvider(
        [
            ToolCall(
                call_id="read-retry",
                tool_name="read_concept",
                arguments={"concept_id": "concept-limits"},
            ),
            ToolCall(
                call_id="read-retry",
                tool_name="read_concept",
                arguments={"concept_id": "concept-limits"},
            ),
            ProviderFinished(),
        ]
    )
    store = AgentEventStore(database)
    with database.connection() as audit_connection:
        asyncio.run(
            AgentOrchestrator(
                event_store=store,
                provider=provider,
                executor=AgentStepExecutor(
                    registry,
                    SQLiteAuditSink(
                        audit_connection,
                        reconciliation_connection_factory=database.connection,
                    ),
                ),
            ).run("run-1")
        )

    events = store.list_events("run-1")
    assert store.get_run("run-1")["status"] == "completed"
    assert tool.executions == 1
    assert [result.fidelity for result in provider.tool_results] == [
        "full",
        "audit_summary",
    ]
    assert [result.replayed for result in provider.tool_results] == [False, True]
    assert [event.event_type for event in events].count("tool_start") == 2
    assert [event.event_type for event in events].count("tool_result") == 1
    assert events[-1].event_type == "done"


def test_same_provider_call_with_changed_arguments_fails_without_reexecution(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    registry = ToolRegistry()
    tool = _CountingReadTool()
    registry.register(tool)
    provider = FixedAutomationProvider(
        [
            ToolCall(
                call_id="read-reused",
                tool_name="read_concept",
                arguments={"concept_id": "concept-limits"},
            ),
            ToolCall(
                call_id="read-reused",
                tool_name="read_concept",
                arguments={"concept_id": "concept-derivatives"},
            ),
            ProviderFinished(),
        ]
    )
    store = AgentEventStore(database)
    with database.connection() as audit_connection:
        asyncio.run(
            AgentOrchestrator(
                event_store=store,
                provider=provider,
                executor=AgentStepExecutor(
                    registry,
                    SQLiteAuditSink(
                        audit_connection,
                        reconciliation_connection_factory=database.connection,
                    ),
                ),
            ).run("run-1")
        )

    events = store.list_events("run-1")
    assert store.get_run("run-1")["status"] == "failed"
    assert store.get_run("run-1")["error_code"] == "value_error"
    assert tool.executions == 1
    assert len(provider.tool_results) == 1
    assert [event.event_type for event in events].count("tool_result") == 1
    assert not any(event.event_type == "done" for event in events)


def test_startup_reconciles_committed_level_two_tool_before_run_interruption(tmp_path):
    database = _database(tmp_path)
    database.seed_demo()
    _create_run(database)
    store = AgentEventStore(database)
    store.start_run(
        "run-1",
        metadata={
            "runId": "run-1",
            "provider": "automation",
            "model": "fixed-actions",
            "providerVersion": "v1",
        },
    )
    store.start_tool_step(
        run_id="run-1",
        step_id="step-recovery",
        ordinal=0,
        invocation_id="inv-recovery",
        tool_name="complete_study_task",
        input_data={
            "toolName": "complete_study_task",
            "callId": "call-recovery",
        },
    )
    registry = ToolRegistry()
    register_initial_product_tools(
        registry,
        connection_factory=database.connection,
        course_id="course-calculus",
        as_of=datetime(2026, 7, 16, 10, tzinfo=UTC),
    )
    with database.connection() as audit_connection:
        sink = SQLiteAuditSink(
            audit_connection,
            reconciliation_connection_factory=database.connection,
        )
        result = asyncio.run(
            AgentStepExecutor(
                registry,
                sink,
                transaction_factory=sink.transaction,
            ).execute_step(
                invocation_id="inv-recovery",
                idempotency_key="tool-recovery",
                tool_name="complete_study_task",
                arguments={
                    "task_id": "task-chain-rule",
                    "course_id": "course-calculus",
                    "expected_revision": 0,
                    "completed_at": "2026-07-16T10:00:00Z",
                },
                context=ToolContext(
                    run_id="run-1",
                    step_id="step-recovery",
                    cancellation_event=asyncio.Event(),
                ),
            )
        )

    assert result.output["status"] == "completed"
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT status FROM agent_steps WHERE id = 'step-recovery'"
            ).fetchone()[0]
            == "running"
        )
        assert (
            connection.execute(
                "SELECT status FROM study_tasks WHERE id = 'task-chain-rule'"
            ).fetchone()[0]
            == "completed"
        )
    assert not any(
        event.event_type in {"tool_result", "state_mutation"}
        for event in store.list_events("run-1")
    )

    assert store.recover_completed_tool_steps() == ["step-recovery"]
    with database.connection() as connection:
        assert AgentRepository(connection).recover_interrupted_runs() == ["run-1"]
    events = store.list_events("run-1")
    event_types = [event.event_type for event in events]
    assert event_types[-4:] == ["tool_result", "state_mutation", "status", "error"]
    mutation = next(event for event in events if event.event_type == "state_mutation")
    assert mutation.payload["entityId"] == "task-chain-rule"
    assert mutation.payload["reversible"] is True
    event_ids = [event.id for event in events]

    assert store.recover_completed_tool_steps() == []
    with database.connection() as connection:
        assert AgentRepository(connection).recover_interrupted_runs() == []
    assert [event.id for event in store.list_events("run-1")] == event_ids


class _ReservationCommitThenRaiseConnection(sqlite3.Connection):
    raise_after_next_commit = False

    def commit(self) -> None:
        super().commit()
        if self.raise_after_next_commit:
            self.raise_after_next_commit = False
            raise RuntimeError("driver raised after reservation commit")


class _ObservableReadTool(_ReadTool):
    def __init__(self) -> None:
        self.executed = False

    async def execute(
        self, arguments: _ReadArguments, context: ToolContext
    ) -> ToolResult:
        self.executed = True
        return await super().execute(arguments, context)


def test_orchestrator_reservation_commit_uncertainty_leaves_no_running_tool(tmp_path):
    database = _database(tmp_path)
    _create_run(database)
    connection = sqlite3.connect(
        database.path,
        timeout=10.0,
        factory=_ReservationCommitThenRaiseConnection,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    tool = _ObservableReadTool()
    registry = ToolRegistry()
    registry.register(tool)
    sink = SQLiteAuditSink(
        connection,
        reconciliation_connection_factory=database.connection,
    )
    connection.raise_after_next_commit = True
    try:
        asyncio.run(
            AgentOrchestrator(
                event_store=AgentEventStore(database),
                provider=FixedAutomationProvider(
                    [
                        ToolCall(
                            call_id="uncertain-reservation",
                            tool_name="read_concept",
                            arguments={"concept_id": "concept-limits"},
                        ),
                        ProviderFinished(),
                    ]
                ),
                executor=AgentStepExecutor(registry, sink),
            ).run("run-1")
        )
    finally:
        connection.close()

    store = AgentEventStore(database)
    events = store.list_events("run-1")
    assert store.get_run("run-1")["status"] == "failed"
    assert tool.executed is False
    assert not any(
        event.event_type in {"tool_result", "state_mutation", "done"}
        for event in events
    )
    with database.connection() as durable:
        repository = AgentRepository(durable)
        invocation = durable.execute(
            "SELECT status, error_code FROM tool_invocations"
        ).fetchone()
        step = durable.execute("SELECT status, error_code FROM agent_steps").fetchone()
        assert tuple(invocation) == ("failed", "reservation_commit_uncertain")
        assert step["status"] == "failed"
        assert repository.recover_interrupted_runs() == []
        assert (
            durable.execute(
                "SELECT count(*) FROM tool_invocations WHERE status = 'running'"
            ).fetchone()[0]
            == 0
        )


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
