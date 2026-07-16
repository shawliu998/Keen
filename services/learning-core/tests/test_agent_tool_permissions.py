from __future__ import annotations

import asyncio

import pytest

from app.agent import (
    AgentStepExecutor,
    ConfirmationRequiredError,
    PermissionLevel,
    StateMutation,
    ToolArguments,
    ToolAuditStart,
    ToolAuditSuccess,
    ToolAuditTerminal,
    ToolContext,
    ToolEffect,
    ToolPermissionError,
    ToolRegistry,
    ToolResult,
)


class EmptyArguments(ToolArguments):
    pass


class MemoryAuditSink:
    def __init__(self) -> None:
        self.started: list[ToolAuditStart] = []
        self.succeeded: list[ToolAuditSuccess] = []
        self.failed: list[ToolAuditTerminal] = []
        self.cancelled: list[ToolAuditTerminal] = []
        self.rejected: list[ToolAuditTerminal] = []

    async def record_started(self, record: ToolAuditStart) -> None:
        self.started.append(record)

    async def record_succeeded(
        self,
        record: ToolAuditSuccess,
        *,
        mutations: tuple[StateMutation, ...],
        transaction: object | None,
    ) -> None:
        self.succeeded.append(record)

    async def record_failed(self, record: ToolAuditTerminal) -> None:
        self.failed.append(record)

    async def record_cancelled(self, record: ToolAuditTerminal) -> None:
        self.cancelled.append(record)

    async def record_rejected(self, record: ToolAuditTerminal) -> None:
        self.rejected.append(record)


def _context() -> ToolContext:
    return ToolContext(
        run_id="run-1",
        step_id="step-1",
        cancellation_event=asyncio.Event(),
    )


class MutatingReadTool:
    name = "mutating_read"
    permission_level = PermissionLevel.AUTOMATIC
    effect = ToolEffect.READ
    arguments_model = EmptyArguments

    async def execute(
        self, arguments: EmptyArguments, context: ToolContext
    ) -> ToolResult:
        return ToolResult(
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
            )
        )


def test_level_one_mutation_is_rejected():
    registry = ToolRegistry()
    registry.register(MutatingReadTool())
    audit = MemoryAuditSink()
    executor = AgentStepExecutor(registry, audit)
    with pytest.raises(ToolPermissionError, match="Level 1"):
        asyncio.run(
            executor.execute_step(
                invocation_id="invocation-1",
                tool_name="mutating_read",
                arguments={},
                context=_context(),
            )
        )
    assert not audit.succeeded
    assert audit.failed[0].error_code == "ToolPermissionError"


class MissingUndoTool:
    name = "missing_undo"
    permission_level = PermissionLevel.LOCAL_REVERSIBLE
    effect = ToolEffect.LOCAL_WRITE
    arguments_model = EmptyArguments

    async def execute(
        self, arguments: EmptyArguments, context: ToolContext
    ) -> ToolResult:
        incomplete = StateMutation.model_construct(
            entity_type="note",
            entity_id="note-1",
            operation="update",
            before={"title": "Before"},
            after={"title": "After"},
        )
        return ToolResult.model_construct(output={}, mutations=(incomplete,))


class NoopTransaction:
    async def __aenter__(self) -> object:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None


def test_level_two_requires_explicit_undo_data_and_transaction():
    registry = ToolRegistry()
    registry.register(MissingUndoTool())
    audit = MemoryAuditSink()
    without_transaction = AgentStepExecutor(registry, audit)
    with pytest.raises(ToolPermissionError, match="transaction"):
        asyncio.run(
            without_transaction.execute_step(
                invocation_id="invocation-no-tx",
                tool_name="missing_undo",
                arguments={},
                context=_context(),
            )
        )
    with pytest.raises(ToolPermissionError, match="before/after/undo"):
        asyncio.run(
            AgentStepExecutor(
                registry, audit, transaction_factory=NoopTransaction
            ).execute_step(
                invocation_id="invocation-no-undo",
                tool_name="missing_undo",
                arguments={},
                context=_context(),
            )
        )


@pytest.mark.parametrize(
    ("operation", "before", "after", "undo", "message"),
    [
        (
            "create",
            {"title": "unexpected"},
            {"title": "after"},
            {
                "operation": "delete",
                "entity_type": "note",
                "entity_id": "note-1",
            },
            "inconsistent before/after",
        ),
        (
            "delete",
            None,
            {"title": "unexpected"},
            {
                "operation": "create",
                "entity_type": "note",
                "entity_id": "note-1",
            },
            "inconsistent before/after",
        ),
        (
            "update",
            None,
            None,
            {
                "operation": "update",
                "entity_type": "note",
                "entity_id": "note-1",
            },
            "inconsistent before/after",
        ),
        (
            "create",
            None,
            {"title": "after"},
            {
                "operation": "update",
                "entity_type": "note",
                "entity_id": "note-1",
            },
            "not the inverse",
        ),
        (
            "create",
            None,
            {"title": "after"},
            {
                "operation": "delete",
                "entity_type": "note",
                "entity_id": "note-2",
            },
            "target must match",
        ),
        (
            "update",
            {"title": "before"},
            {"title": "after"},
            {
                "operation": "update",
                "entity_type": "note",
                "entity_id": "note-1",
                "restore": {"title": "wrong"},
            },
            "restore state does not match",
        ),
    ],
)
def test_state_mutation_requires_an_executable_inverse(
    operation, before, after, undo, message
):
    with pytest.raises(ValueError, match=message):
        StateMutation(
            entity_type="note",
            entity_id="note-1",
            operation=operation,
            before=before,
            after=after,
            undo=undo,
        )


class LevelThreeTool:
    name = "export_notes"
    permission_level = PermissionLevel.CONFIRM_FIRST
    effect = ToolEffect.EXTERNAL_OR_DESTRUCTIVE
    arguments_model = EmptyArguments

    def __init__(self) -> None:
        self.executed = False

    async def execute(
        self, arguments: EmptyArguments, context: ToolContext
    ) -> ToolResult:
        self.executed = True
        return ToolResult()


def test_level_three_is_fail_closed_and_never_executes():
    tool = LevelThreeTool()
    registry = ToolRegistry()
    registry.register(tool)
    audit = MemoryAuditSink()
    with pytest.raises(ConfirmationRequiredError, match="unavailable"):
        asyncio.run(
            AgentStepExecutor(registry, audit).execute_step(
                invocation_id="invocation-3",
                tool_name="export_notes",
                arguments={},
                context=_context(),
            )
        )
    assert tool.executed is False
    assert audit.started[0].permission_level is PermissionLevel.CONFIRM_FIRST
    assert audit.rejected[0].error_code == "permission_denied"
