from __future__ import annotations

import asyncio
import contextlib
import re
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.repositories.agent_repository import AgentRepository
from app.repositories.task_repository import TaskRepository

from .audit import (
    ToolAuditStart,
    ToolAuditSuccess,
    ToolAuditTerminal,
    summarize_for_audit,
    summarize_mutation,
)
from .sqlite_audit import SQLiteAuditSink
from .transaction import SQLiteToolSession
from .types import (
    PermissionLevel,
    StateMutation,
    ToolReplayResult,
    ToolResult,
    UndoInstruction,
)


class UndoHandler(Protocol):
    async def execute(
        self,
        instruction: UndoInstruction,
        *,
        expected_current: dict[str, object] | None,
        transaction: SQLiteToolSession,
    ) -> StateMutation: ...


class UndoRegistry:
    """Allowlist of trusted, entity-specific inverse implementations."""

    def __init__(self) -> None:
        self._handlers: dict[str, UndoHandler] = {}

    def register(self, entity_type: str, handler: UndoHandler) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", entity_type) is None:
            raise ValueError("undo entity type is invalid")
        if entity_type in self._handlers:
            raise ValueError(f"duplicate undo handler: {entity_type}")
        if not callable(getattr(handler, "execute", None)):
            raise TypeError("undo handler must implement execute")
        self._handlers[entity_type] = handler

    def get(self, entity_type: str) -> UndoHandler:
        try:
            return self._handlers[entity_type]
        except KeyError as error:
            raise PermissionError(
                f"undo is not available for entity type {entity_type}"
            ) from error


class _StudyTaskSnapshot(BaseModel):
    """Exact decoded TaskRepository shape accepted by the task undo handler."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=256)
    course_id: str = Field(min_length=1, max_length=256)
    concept_id: str | None = Field(default=None, max_length=256)
    title: str
    reason: str
    due_at: str
    estimated_minutes: int = Field(gt=0)
    status: str
    created_at: str
    updated_at: str
    source_type: str
    source_id: str | None
    priority_score: float
    priority_components: dict[str, object]
    recommended_reason: str
    scheduled_for: str | None
    completed_at: str | None
    snoozed_until: str | None
    idempotency_key: str | None
    creation_payload: dict[str, object] | None
    revision: int = Field(ge=0)


class StudyTaskUndoHandler:
    """Restore a completed study task through one explicit optimistic update."""

    async def execute(
        self,
        instruction: UndoInstruction,
        *,
        expected_current: dict[str, object] | None,
        transaction: SQLiteToolSession,
    ) -> StateMutation:
        if instruction.operation != "update" or instruction.restore is None:
            raise PermissionError("study task undo only supports typed updates")
        if expected_current is None:
            raise ValueError("study task undo requires the recorded current state")
        restore = _StudyTaskSnapshot.model_validate(instruction.restore).model_dump(
            mode="python"
        )
        expected = _StudyTaskSnapshot.model_validate(expected_current).model_dump(
            mode="python"
        )
        repository = TaskRepository(transaction)
        current = repository.get(instruction.entity_id)
        if current != expected:
            raise ValueError("study task changed after the recorded mutation")
        if (
            restore["id"] != instruction.entity_id
            or expected["id"] != instruction.entity_id
        ):
            raise ValueError("study task undo target does not match its snapshot")
        mutable = {"status", "completed_at", "updated_at", "revision"}
        if any(restore[key] != expected[key] for key in restore.keys() - mutable):
            raise PermissionError(
                "study task undo cannot rewrite immutable task fields"
            )
        status_pair = {expected["status"], restore["status"]}
        if "completed" not in status_pair or not status_pair.intersection(
            {"upcoming", "overdue"}
        ):
            raise ValueError(
                "study task undo snapshots are not a completion transition"
            )
        restored_revision = expected["revision"] + 1
        restored_updated_at = datetime.now(UTC).isoformat()
        cursor = transaction.execute(
            """
            UPDATE study_tasks
            SET status = ?, completed_at = ?, updated_at = ?, revision = ?
            WHERE id = ? AND status = ? AND completed_at IS ?
              AND updated_at = ? AND revision = ?
            """,
            (
                restore["status"],
                restore["completed_at"],
                restored_updated_at,
                restored_revision,
                instruction.entity_id,
                expected["status"],
                expected["completed_at"],
                expected["updated_at"],
                expected["revision"],
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("study task changed concurrently during undo")
        restored = repository.get(instruction.entity_id)
        expected_restored = {
            **restore,
            "updated_at": restored_updated_at,
            "revision": restored_revision,
        }
        if restored != expected_restored:
            raise RuntimeError("study task undo did not restore the recorded semantics")
        return StateMutation(
            entity_type="study_task",
            entity_id=instruction.entity_id,
            operation="update",
            before=expected,
            after=expected_restored,
            undo={
                "operation": "update",
                "entity_type": "study_task",
                "entity_id": instruction.entity_id,
                "restore": expected,
            },
        )


class UndoExecutor:
    def __init__(self, audit_sink: SQLiteAuditSink, registry: UndoRegistry) -> None:
        self._audit_sink = audit_sink
        self._repository = AgentRepository(audit_sink.connection)
        self._registry = registry

    async def execute(
        self,
        *,
        run_id: str,
        step_id: str,
        mutation_id: str,
        invocation_id: str,
        idempotency_key: str,
        cancellation_event: asyncio.Event,
    ) -> ToolResult | ToolReplayResult:
        if cancellation_event.is_set():
            raise asyncio.CancelledError
        arguments = {"mutation_id": mutation_id}
        reservation = await self._audit_sink.record_started(
            ToolAuditStart(
                invocation_id=invocation_id,
                run_id=run_id,
                step_id=step_id,
                tool_name="undo_state_mutation",
                permission_level=PermissionLevel.LOCAL_REVERSIBLE,
                arguments=summarize_for_audit(arguments),
                idempotency_key=idempotency_key,
            )
        )
        if reservation.disposition == "replay":
            return ToolReplayResult(
                invocation_id=reservation.invocation_id,
                result_summary=reservation.result_summary or {},
                mutation_ids=reservation.mutation_ids,
            )
        terminal = ToolAuditTerminal(
            invocation_id=invocation_id,
            error_code="undo_failed",
        )
        try:
            async with self._audit_sink.transaction() as transaction:
                if cancellation_event.is_set():
                    raise asyncio.CancelledError
                original = self._repository.get_state_mutation(mutation_id)
                if original["run_id"] != run_id:
                    raise PermissionError("state mutation does not belong to this run")
                if not original["reversible"] or original["undo"] is None:
                    raise PermissionError("state mutation is not reversible")
                if original["undone_at"] is not None:
                    raise ValueError("state mutation has already been undone")
                original_mutation = StateMutation.model_validate(
                    {
                        "entity_type": original["entity_type"],
                        "entity_id": original["entity_id"],
                        "operation": original["operation"],
                        "before": original["before"],
                        "after": original["after"],
                        "undo": original["undo"],
                    }
                )
                instruction = original_mutation.undo
                handler = self._registry.get(instruction.entity_type)
                inverse = await handler.execute(
                    instruction,
                    expected_current=original_mutation.after,
                    transaction=transaction,
                )
                self._validate_inverse(original, instruction, inverse)
                if cancellation_event.is_set():
                    raise asyncio.CancelledError
                result = ToolResult(
                    output={
                        "undone_mutation_id": mutation_id,
                        "entity_type": inverse.entity_type,
                        "entity_id": inverse.entity_id,
                    },
                    mutations=(inverse,),
                )
                await self._audit_sink.record_succeeded(
                    ToolAuditSuccess(
                        invocation_id=invocation_id,
                        result=summarize_for_audit(result.output),
                        mutations=(summarize_mutation(inverse),),
                    ),
                    mutations=result.mutations,
                    transaction=transaction,
                )
                self._repository.mark_state_mutation_undone(
                    mutation_id,
                    undo_invocation_id=invocation_id,
                    commit=False,
                )
                return result
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await self._audit_sink.record_cancelled(
                    terminal.model_copy(update={"error_code": "cancelled"})
                )
            raise
        except Exception as error:
            try:
                await self._audit_sink.record_failed(
                    terminal.model_copy(update={"error_code": type(error).__name__})
                )
            except Exception:
                error.add_note("The terminal undo audit could not be recorded")
            raise

    @staticmethod
    def _validate_inverse(
        original: dict,
        instruction: UndoInstruction,
        inverse: StateMutation,
    ) -> None:
        if (
            inverse.entity_type != instruction.entity_type
            or inverse.entity_id != instruction.entity_id
            or inverse.operation != instruction.operation
        ):
            raise PermissionError("undo handler returned a mutation for another target")
        expected_before = original["after"]
        expected_after = original["before"]
        if inverse.before != expected_before:
            raise PermissionError(
                "undo handler result does not match recorded snapshots"
            )
        if not isinstance(expected_after, dict) or not isinstance(inverse.after, dict):
            if inverse.after != expected_after:
                raise PermissionError(
                    "undo handler result does not match recorded snapshots"
                )
            return
        technical_fields = {"revision", "updated_at"}
        expected_business = {
            key: value
            for key, value in expected_after.items()
            if key not in technical_fields
        }
        inverse_business = {
            key: value
            for key, value in inverse.after.items()
            if key not in technical_fields
        }
        if expected_business != inverse_business:
            raise PermissionError(
                "undo handler result does not match recorded snapshots"
            )
        expected_revision = expected_before.get("revision")
        inverse_revision = inverse.after.get("revision")
        if (
            not isinstance(expected_revision, int)
            or isinstance(expected_revision, bool)
            or inverse_revision != expected_revision + 1
        ):
            raise PermissionError("undo handler must advance the entity revision")


def default_undo_registry() -> UndoRegistry:
    registry = UndoRegistry()
    registry.register("study_task", StudyTaskUndoHandler())
    return registry
