from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Mapping

from pydantic import ValidationError

from ..agent.executor import ToolArgumentValidationError
from ..agent.sqlite_audit import mutation_id_for_invocation
from ..agent.tools.product import (
    CompleteStudyTaskArguments,
    CompleteStudyTaskProposalArguments,
    CompleteStudyTaskScopedArguments,
    CompleteStudyTaskTool,
)
from ..agent.transaction import SQLiteToolSession
from ..agent.types import ToolContext
from ..database import Database
from ..repositories import dump_json
from ..repositories.agent_repository import AgentRepository

_TOOL_NAME = "complete_study_task"
_TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


class Level2ApprovalNotFoundError(LookupError):
    pass


class Level2ApprovalConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Level2ApprovalResult:
    approval_id: str
    run_id: str
    status: Literal["approved", "denied", "expired", "cancelled"]
    resolution: Literal["confirm", "reject"]
    replayed: bool
    summary: dict[str, str]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def _arguments(arguments: Mapping[str, object]) -> CompleteStudyTaskProposalArguments:
    try:
        return CompleteStudyTaskProposalArguments.model_validate(dict(arguments))
    except ValidationError as error:
        raise ToolArgumentValidationError("tool arguments are invalid") from error


def _canonical(
    arguments: CompleteStudyTaskScopedArguments,
) -> tuple[dict[str, object], str]:
    canonical = arguments.model_dump(mode="json")
    serialized = dump_json(canonical)
    return canonical, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class Level2ApprovalService:
    """Host-owned proposal and execution path for the one Level 2 action.

    Provider output can create a proposal only.  Exact arguments stay in the
    private action row; events and HTTP responses contain only resolved titles
    and fixed effects.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_pending(self, *, run_id: str | None = None) -> list[dict]:
        with self._database.connection() as connection:
            where = "WHERE a.status = 'pending'"
            params: tuple[object, ...] = ()
            if run_id is not None:
                where += " AND a.run_id = ?"
                params = (run_id,)
            rows = connection.execute(
                f"""
                SELECT a.id, a.run_id, a.summary, a.requested_at, x.tool_name
                FROM approval_requests AS a
                JOIN level2_approval_actions AS x ON x.approval_id = a.id
                {where}
                ORDER BY a.requested_at, a.id
                """,
                params,
            ).fetchall()
        return [
            {
                "approval_id": str(row["id"]),
                "tool_name": str(row["tool_name"]),
                "summary": self._summary_value(str(row["summary"])),
            }
            for row in rows
        ]

    async def propose(
        self,
        *,
        run_id: str,
        call_id: str,
        arguments: Mapping[str, object],
    ) -> str:
        proposed = _arguments(arguments)
        stable = hashlib.sha256(f"{run_id}\0{call_id}".encode()).hexdigest()
        proposal_step_id = f"step-proposal-{stable}"
        proposal_invocation_id = f"inv-proposal-{stable}"
        approval_id = f"approval-{stable}"
        now = _now()
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                run = repository.get_run(run_id)
                if run is None:
                    raise Level2ApprovalNotFoundError("Agent run was not found")
                if run["status"] != "running":
                    raise Level2ApprovalConflictError(
                        "Agent run is not accepting approvals"
                    )
                if run["course_scope_id"] is None:
                    raise ToolArgumentValidationError("tool arguments are invalid")
                validated = CompleteStudyTaskScopedArguments(
                    task_id=proposed.task_id,
                    course_id=run["course_scope_id"],
                    expected_revision=proposed.expected_revision,
                )
                canonical, arguments_hash = _canonical(validated)
                summary = self._summary(
                    connection,
                    validated.task_id,
                    validated.course_id,
                    validated.expected_revision,
                )
                if summary is None:
                    raise ToolArgumentValidationError("tool arguments are invalid")
                existing = connection.execute(
                    "SELECT approval_id FROM level2_approval_actions WHERE approval_id = ?",
                    (approval_id,),
                ).fetchone()
                if existing is not None:
                    connection.commit()
                    return approval_id
                ordinal = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(ordinal), -1) + 1 FROM agent_steps WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()[0]
                )
                repository.add_step(
                    step_id=proposal_step_id,
                    run_id=run_id,
                    ordinal=ordinal,
                    kind="tool",
                    label=_TOOL_NAME,
                    input_data={"toolName": _TOOL_NAME, "phase": "proposal"},
                    commit=False,
                )
                connection.execute(
                    "UPDATE agent_steps SET status = 'completed', output_json = ?, updated_at = ?, finished_at = ? WHERE id = ?",
                    (
                        dump_json({"effect": "approval_requested"}),
                        now,
                        now,
                        proposal_step_id,
                    ),
                )
                repository.start_tool_invocation(
                    invocation_id=proposal_invocation_id,
                    run_id=run_id,
                    step_id=proposal_step_id,
                    tool_name=_TOOL_NAME,
                    permission_level=2,
                    arguments=canonical,
                    idempotency_key=f"proposal-{stable}",
                    commit=False,
                )
                repository.finish_tool_invocation(
                    proposal_invocation_id,
                    status="denied",
                    error_code="approval_required",
                    commit=False,
                )
                connection.execute(
                    "INSERT INTO approval_requests (id, run_id, tool_invocation_id, status, summary, requested_at, resolved_at) VALUES (?, ?, ?, 'pending', ?, ?, NULL)",
                    (
                        approval_id,
                        run_id,
                        proposal_invocation_id,
                        dump_json(summary),
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO level2_approval_actions (approval_id, run_id, tool_name, canonical_arguments_json, arguments_hash, execution_invocation_id, resolution_kind, resolution_idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?)",
                    (
                        approval_id,
                        run_id,
                        _TOOL_NAME,
                        dump_json(canonical),
                        arguments_hash,
                        now,
                    ),
                )
                self._event(
                    repository,
                    run_id,
                    "tool_start",
                    {
                        "invocationId": proposal_invocation_id,
                        "toolName": _TOOL_NAME,
                        "replayCandidate": False,
                    },
                    proposal_step_id,
                    "start",
                )
                self._event(
                    repository,
                    run_id,
                    "tool_result",
                    {
                        "callId": call_id,
                        "invocationId": proposal_invocation_id,
                        "toolName": _TOOL_NAME,
                        "result": {"effect": "approval_required"},
                        "truncated": False,
                        "replayed": False,
                    },
                    proposal_step_id,
                    "result",
                )
                self._event(
                    repository,
                    run_id,
                    "checkpoint",
                    {
                        "label": "approval_requested",
                        "data": {
                            "approvalId": approval_id,
                            "toolName": _TOOL_NAME,
                            "summary": summary,
                        },
                    },
                    approval_id,
                    "checkpoint",
                )
                repository.transition_run(
                    run_id, status="waiting_approval", commit=False
                )
                self._event(
                    repository,
                    run_id,
                    "status",
                    {"status": "waiting_approval"},
                    approval_id,
                    "status",
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return approval_id

    async def resolve(
        self,
        *,
        run_id: str,
        approval_id: str,
        resolution: Literal["confirm", "reject"],
        idempotency_key: str,
    ) -> Level2ApprovalResult:
        if resolution == "reject":
            return self._reject(run_id, approval_id, idempotency_key)
        return await self._confirm(run_id, approval_id, idempotency_key)

    def cancel_waiting(self, run_id: str) -> bool:
        now = _now()
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                run = repository.get_run(run_id)
                if run is None:
                    raise Level2ApprovalNotFoundError("Agent run was not found")
                if run["status"] != "waiting_approval":
                    connection.rollback()
                    return False
                pending = connection.execute(
                    "SELECT id FROM approval_requests WHERE run_id = ? AND status = 'pending'",
                    (run_id,),
                ).fetchone()
                if pending is None:
                    raise Level2ApprovalConflictError(
                        "Agent approval is no longer pending"
                    )
                approval_id = str(pending["id"])
                cursor = connection.execute(
                    "UPDATE approval_requests SET status = 'cancelled', resolved_at = ? WHERE run_id = ? AND status = 'pending'",
                    (now, run_id),
                )
                if cursor.rowcount != 1:
                    raise Level2ApprovalConflictError(
                        "Agent approval is no longer pending"
                    )
                repository.transition_run(
                    run_id,
                    status="cancelled",
                    error_code="cancelled",
                    error_detail="Agent approval was cancelled",
                    commit=False,
                )
                self._event(
                    repository,
                    run_id,
                    "checkpoint",
                    {
                        "label": "approval_resolved",
                        "data": {
                            "approvalId": approval_id,
                            "status": "cancelled",
                        },
                    },
                    approval_id,
                    "cancelled",
                )
                self._event(
                    repository,
                    run_id,
                    "status",
                    {"status": "cancelled"},
                    run_id,
                    "cancel-status",
                )
                self._event(
                    repository,
                    run_id,
                    "error",
                    {
                        "code": "cancelled",
                        "retryable": False,
                        "status": "cancelled",
                        "message": "Approval was cancelled; no study task was changed.",
                    },
                    run_id,
                    "cancel-error",
                )
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise

    async def _confirm(
        self, run_id: str, approval_id: str, idempotency_key: str
    ) -> Level2ApprovalResult:
        # The transaction intentionally spans the trusted tool call. It is local,
        # bounded, cancellation-free host code, and makes audit, domain mutation,
        # approval resolution, and terminal events one atomic commit.
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                action, approval, run = self._locked_action(
                    repository, run_id, approval_id
                )
                replay = self._replay_or_conflict(
                    action,
                    approval,
                    resolution="confirm",
                    idempotency_key=idempotency_key,
                )
                if replay is not None:
                    connection.rollback()
                    return replay
                if (
                    approval["status"] != "pending"
                    or run["status"] != "waiting_approval"
                ):
                    raise Level2ApprovalConflictError("Approval is no longer pending")
                stored_arguments = self._validated_action(action, run)
                arguments = CompleteStudyTaskArguments(
                    **stored_arguments.model_dump(mode="python"),
                    completed_at=datetime.now(UTC),
                )
                execution_id = _stable_id("inv-execution", approval_id)
                step_id = _stable_id("step-execution", approval_id)
                ordinal = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(ordinal), -1) + 1 FROM agent_steps WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()[0]
                )
                now = _now()
                repository.add_step(
                    step_id=step_id,
                    run_id=run_id,
                    ordinal=ordinal,
                    kind="tool",
                    label=_TOOL_NAME,
                    input_data={"toolName": _TOOL_NAME, "phase": "execution"},
                    commit=False,
                )
                connection.execute(
                    "UPDATE agent_steps SET status = 'running', updated_at = ?, started_at = ? WHERE id = ?",
                    (now, now, step_id),
                )
                canonical, _ = _canonical(arguments)
                repository.start_tool_invocation(
                    invocation_id=execution_id,
                    run_id=run_id,
                    step_id=step_id,
                    tool_name=_TOOL_NAME,
                    permission_level=2,
                    arguments=canonical,
                    idempotency_key=f"execution-{approval_id}",
                    commit=False,
                )
                connection.execute(
                    "UPDATE level2_approval_actions SET execution_invocation_id = ?, resolution_kind = 'confirm', resolution_idempotency_key = ? WHERE approval_id = ?",
                    (execution_id, idempotency_key, approval_id),
                )
                token = object()
                result = await CompleteStudyTaskTool().execute(
                    arguments,
                    ToolContext(
                        run_id=run_id,
                        step_id=step_id,
                        cancellation_event=asyncio.Event(),
                        transaction=SQLiteToolSession(connection, token),
                    ),
                )
                # CompleteStudyTaskTool returns the closed output and reversible mutation contract.
                repository.complete_tool_invocation(
                    execution_id,
                    result_summary={"effect": "study_task_completed"},
                    mutations=[
                        {
                            "id": mutation_id_for_invocation(execution_id, index),
                            "entity_type": item.entity_type,
                            "entity_id": item.entity_id,
                            "operation": item.operation,
                            "before": item.before,
                            "after": item.after,
                            "undo": item.undo.model_dump(mode="json"),
                            "reversible": True,
                        }
                        for index, item in enumerate(result.mutations)
                    ],
                    commit=False,
                )
                connection.execute(
                    "UPDATE agent_steps SET status = 'completed', output_json = ?, updated_at = ?, finished_at = ? WHERE id = ?",
                    (dump_json({"effect": "study_task_completed"}), now, now, step_id),
                )
                cursor = connection.execute(
                    "UPDATE approval_requests SET status = 'approved', resolved_at = ? WHERE id = ? AND status = 'pending'",
                    (now, approval_id),
                )
                if cursor.rowcount != 1:
                    raise Level2ApprovalConflictError("Approval is no longer pending")
                repository.transition_run(run_id, status="running", commit=False)
                repository.transition_run(run_id, status="completed", commit=False)
                execution_call_id = f"approval:{approval_id}"
                self._event(
                    repository,
                    run_id,
                    "tool_start",
                    {
                        "invocationId": execution_id,
                        "toolName": _TOOL_NAME,
                        "replayCandidate": False,
                    },
                    step_id,
                    "start",
                )
                self._event(
                    repository,
                    run_id,
                    "checkpoint",
                    {
                        "label": "approval_resolved",
                        "data": {
                            "approvalId": approval_id,
                            "status": "approved",
                            "executionInvocationId": execution_id,
                        },
                    },
                    approval_id,
                    "resolved",
                )
                self._event(
                    repository,
                    run_id,
                    "tool_result",
                    {
                        "callId": execution_call_id,
                        "invocationId": execution_id,
                        "toolName": _TOOL_NAME,
                        "result": {"effect": "study_task_completed"},
                        "truncated": False,
                        "replayed": False,
                    },
                    step_id,
                    "result",
                )
                self._event(
                    repository,
                    run_id,
                    "state_mutation",
                    {
                        "callId": execution_call_id,
                        "invocationId": execution_id,
                        "mutationId": mutation_id_for_invocation(execution_id, 0),
                        "entityType": "study_task",
                        "entityId": arguments.task_id,
                        "operation": "update",
                        "reversible": True,
                    },
                    step_id,
                    "mutation",
                )
                self._event(
                    repository,
                    run_id,
                    "status",
                    {"status": "completed"},
                    approval_id,
                    "completed",
                )
                self._event(
                    repository,
                    run_id,
                    "done",
                    {"status": "completed"},
                    approval_id,
                    "done",
                )
                connection.commit()
                return Level2ApprovalResult(
                    approval_id,
                    run_id,
                    "approved",
                    "confirm",
                    False,
                    self._summary_value(str(approval["summary"])),
                )
            except (
                LookupError,
                ToolArgumentValidationError,
                ValidationError,
            ):
                connection.rollback()
                return self._expire(run_id, approval_id, idempotency_key)
            except ValueError as error:
                connection.rollback()
                if (
                    str(error)
                    != "study task is missing, completed, or updated concurrently"
                ):
                    raise
                return self._expire(run_id, approval_id, idempotency_key)
            except Exception:
                connection.rollback()
                raise

    def _reject(
        self, run_id: str, approval_id: str, idempotency_key: str
    ) -> Level2ApprovalResult:
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                action, approval, run = self._locked_action(
                    repository, run_id, approval_id
                )
                replay = self._replay_or_conflict(
                    action,
                    approval,
                    resolution="reject",
                    idempotency_key=idempotency_key,
                )
                if replay is not None:
                    connection.rollback()
                    return replay
                if (
                    approval["status"] != "pending"
                    or run["status"] != "waiting_approval"
                ):
                    raise Level2ApprovalConflictError("Approval is no longer pending")
                now = _now()
                connection.execute(
                    "UPDATE level2_approval_actions SET resolution_kind = 'reject', resolution_idempotency_key = ? WHERE approval_id = ?",
                    (idempotency_key, approval_id),
                )
                connection.execute(
                    "UPDATE approval_requests SET status = 'denied', resolved_at = ? WHERE id = ? AND status = 'pending'",
                    (now, approval_id),
                )
                repository.transition_run(
                    run_id,
                    status="cancelled",
                    error_code="approval_denied",
                    error_detail="The requested local study-task completion was not approved",
                    commit=False,
                )
                self._event(
                    repository,
                    run_id,
                    "checkpoint",
                    {
                        "label": "approval_resolved",
                        "data": {
                            "approvalId": approval_id,
                            "status": "denied",
                        },
                    },
                    approval_id,
                    "rejected",
                )
                self._event(
                    repository,
                    run_id,
                    "status",
                    {"status": "cancelled"},
                    approval_id,
                    "denied-status",
                )
                self._event(
                    repository,
                    run_id,
                    "error",
                    {
                        "code": "approval_denied",
                        "retryable": False,
                        "status": "cancelled",
                        "message": "Approval was declined; no study task was changed.",
                    },
                    approval_id,
                    "denied-error",
                )
                connection.commit()
                return Level2ApprovalResult(
                    approval_id,
                    run_id,
                    "denied",
                    "reject",
                    False,
                    self._summary_value(str(approval["summary"])),
                )
            except Exception:
                connection.rollback()
                raise

    def _expire(
        self, run_id: str, approval_id: str, idempotency_key: str
    ) -> Level2ApprovalResult:
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                action, approval, run = self._locked_action(
                    repository, run_id, approval_id
                )
                replay = self._replay_or_conflict(
                    action,
                    approval,
                    resolution="confirm",
                    idempotency_key=idempotency_key,
                )
                if replay is not None:
                    connection.rollback()
                    return replay
                if (
                    approval["status"] != "pending"
                    or run["status"] != "waiting_approval"
                ):
                    raise Level2ApprovalConflictError("Approval is no longer pending")
                now = _now()
                connection.execute(
                    "UPDATE level2_approval_actions SET resolution_kind = 'confirm', resolution_idempotency_key = ? WHERE approval_id = ?",
                    (idempotency_key, approval_id),
                )
                connection.execute(
                    "UPDATE approval_requests SET status = 'expired', resolved_at = ? WHERE id = ?",
                    (now, approval_id),
                )
                repository.transition_run(
                    run_id,
                    status="failed",
                    error_code="approval_action_expired",
                    error_detail="The requested study task changed before approval could be applied",
                    commit=False,
                )
                self._event(
                    repository,
                    run_id,
                    "checkpoint",
                    {
                        "label": "approval_resolved",
                        "data": {
                            "approvalId": approval_id,
                            "status": "expired",
                        },
                    },
                    approval_id,
                    "expired",
                )
                self._event(
                    repository,
                    run_id,
                    "status",
                    {"status": "failed"},
                    approval_id,
                    "expired-status",
                )
                self._event(
                    repository,
                    run_id,
                    "error",
                    {
                        "code": "approval_action_expired",
                        "retryable": False,
                        "status": "failed",
                        "message": "The study task changed before approval; no change was applied.",
                    },
                    approval_id,
                    "expired-error",
                )
                connection.commit()
                return Level2ApprovalResult(
                    approval_id,
                    run_id,
                    "expired",
                    "confirm",
                    False,
                    self._summary_value(str(approval["summary"])),
                )
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _summary(
        connection: sqlite3.Connection,
        task_id: str,
        course_id: str,
        expected_revision: int,
    ) -> dict[str, str] | None:
        row = connection.execute(
            "SELECT t.title AS task_title, c.title AS course_title FROM study_tasks AS t JOIN courses AS c ON c.id = t.course_id WHERE t.id = ? AND t.course_id = ? AND t.status != 'completed' AND t.revision = ?",
            (task_id, course_id, expected_revision),
        ).fetchone()
        if row is None:
            return None
        return {
            "title": "Complete study task",
            "taskTitle": str(row["task_title"]),
            "courseTitle": str(row["course_title"]),
            "effect": "Marks this local study task complete. You can undo this change.",
        }

    @staticmethod
    def _summary_value(value: str) -> dict[str, str]:
        parsed = json.loads(value)
        if (
            not isinstance(parsed, dict)
            or set(parsed) != {"title", "taskTitle", "courseTitle", "effect"}
            or not all(isinstance(item, str) for item in parsed.values())
        ):
            raise ValueError("stored approval summary is invalid")
        return {
            "title": parsed["title"],
            "taskTitle": parsed["taskTitle"],
            "courseTitle": parsed["courseTitle"],
            "effect": parsed["effect"],
        }

    @staticmethod
    def _event(
        repository: AgentRepository,
        run_id: str,
        event_type: str,
        payload: dict[str, object],
        stable: str,
        suffix: str,
    ) -> None:
        repository.append_event(
            event_id=_stable_id("event-approval", stable, suffix),
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            commit=False,
        )

    @staticmethod
    def _locked_action(repository: AgentRepository, run_id: str, approval_id: str):
        row = repository.connection.execute(
            "SELECT x.*, a.status AS approval_status, a.summary, a.run_id AS approval_run_id, r.status AS run_status, r.course_scope_id FROM level2_approval_actions AS x JOIN approval_requests AS a ON a.id = x.approval_id JOIN agent_runs AS r ON r.id = x.run_id WHERE x.approval_id = ? AND x.run_id = ?",
            (approval_id, run_id),
        ).fetchone()
        if row is None:
            raise Level2ApprovalNotFoundError(
                "Approval was not found for this Agent run"
            )
        action = dict(row)
        return (
            action,
            {"status": row["approval_status"], "summary": row["summary"]},
            {"status": row["run_status"], "course_scope_id": row["course_scope_id"]},
        )

    @staticmethod
    def _replay_or_conflict(
        action: dict,
        approval: dict,
        *,
        resolution: Literal["confirm", "reject"],
        idempotency_key: str,
    ) -> Level2ApprovalResult | None:
        old_key = action["resolution_idempotency_key"]
        if old_key is None:
            return None
        if old_key != idempotency_key or action["resolution_kind"] != resolution:
            raise Level2ApprovalConflictError(
                "Approval was already resolved with a different request"
            )
        status = str(approval["status"])
        if status not in {"approved", "denied", "expired", "cancelled"}:
            raise Level2ApprovalConflictError("Approval resolution is not durable")
        return Level2ApprovalResult(
            str(action["approval_id"]),
            str(action["run_id"]),
            status,
            resolution,
            True,
            Level2ApprovalService._summary_value(str(approval["summary"])),
        )

    @staticmethod
    def _validated_action(action: dict, run: dict) -> CompleteStudyTaskScopedArguments:
        try:
            payload = json.loads(str(action["canonical_arguments_json"]))
        except json.JSONDecodeError as error:
            raise ToolArgumentValidationError(
                "stored approval arguments are invalid"
            ) from error
        try:
            arguments = CompleteStudyTaskScopedArguments.model_validate(payload)
        except ValidationError as error:
            raise ToolArgumentValidationError(
                "stored approval arguments are invalid"
            ) from error
        canonical, digest = _canonical(arguments)
        if (
            dump_json(canonical) != str(action["canonical_arguments_json"])
            or digest != action["arguments_hash"]
            or run["course_scope_id"] != arguments.course_id
        ):
            raise ToolArgumentValidationError("stored approval arguments are invalid")
        return arguments


__all__ = [
    "Level2ApprovalConflictError",
    "Level2ApprovalNotFoundError",
    "Level2ApprovalResult",
    "Level2ApprovalService",
]
