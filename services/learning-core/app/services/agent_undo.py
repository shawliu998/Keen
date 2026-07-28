from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ..agent.audit import summarize_for_audit
from ..agent.event_stream import AgentEventStore
from ..agent.sqlite_audit import (
    InFlightInvocationError,
    SQLiteAuditSink,
    TerminalInvocationError,
)
from ..agent.types import PermissionLevel, ToolReplayResult
from ..agent.undo import UndoExecutor, default_undo_registry
from ..database import Database
from ..repositories.agent_repository import AgentRepository

UndoAction = Literal["undo", "redo"]
_TOOL_NAME = "undo_state_mutation"
_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


class AgentUndoNotFoundError(LookupError):
    pass


class AgentUndoConflictError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AgentUndoForbiddenError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class AgentUndoResult:
    action: UndoAction
    run_id: str
    target_mutation_id: str
    invocation_id: str
    mutation_id: str
    entity_type: str
    entity_id: str
    operation: str
    replayed: bool


class AgentUndoService:
    """Execute allowlisted local mutation inverses without client-supplied state."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._events = AgentEventStore(database)
        self._lock = asyncio.Lock()

    async def execute(
        self,
        *,
        action: UndoAction,
        run_id: str,
        mutation_id: str,
        idempotency_key: str,
    ) -> AgentUndoResult:
        async with self._lock:
            with self._database.connection() as connection:
                repository = AgentRepository(connection)
                run = repository.get_run(run_id)
                if run is None:
                    raise AgentUndoNotFoundError("Agent run was not found")
                if run["status"] not in _TERMINAL_RUN_STATUSES:
                    raise AgentUndoConflictError(
                        "run_not_terminal",
                        "The Agent run must finish before its mutations can be changed",
                    )
                requested = self._mutation_for_run(
                    repository, run_id=run_id, mutation_id=mutation_id
                )
                effective = self._effective_mutation(
                    repository, requested=requested, action=action
                )
                invocation_id, step_id = self._stable_ids(
                    run_id,
                    idempotency_key,
                    action=action,
                    target_mutation_id=mutation_id,
                )
                idempotency_hash = self._idempotency_hash(run_id, idempotency_key)
                arguments = {"mutation_id": effective["id"]}
                arguments_hash = summarize_for_audit(arguments).sha256
                existing = repository.find_tool_invocation(
                    run_id=run_id, idempotency_key=idempotency_key
                )
                if existing is not None:
                    self._validate_existing_invocation(
                        existing,
                        step_id=step_id,
                        arguments_hash=arguments_hash,
                    )
                    if existing["status"] in {"pending", "running"}:
                        raise AgentUndoConflictError(
                            "undo_in_progress",
                            "This mutation action is already in progress",
                        )
                    if existing["status"] != "succeeded":
                        raise AgentUndoConflictError(
                            "idempotency_key_terminal",
                            "This idempotency key belongs to an unsuccessful action; use a new key",
                        )
                    mutations = repository.list_state_mutations(existing["id"])
                    if len(mutations) != 1:
                        raise RuntimeError(
                            "A completed mutation action has invalid audit state"
                        )
                    applied = mutations[0]
                    self._complete_step_if_needed(
                        action=action,
                        run_id=run_id,
                        step_id=step_id,
                        invocation_id=existing["id"],
                        target_mutation_id=mutation_id,
                        applied=applied,
                        replayed=True,
                    )
                    return self._result(
                        action=action,
                        run_id=run_id,
                        target_mutation_id=mutation_id,
                        invocation_id=existing["id"],
                        applied=applied,
                        replayed=True,
                    )

                self._validate_actionable(effective)
                self._validate_step_available(
                    connection,
                    run_id=run_id,
                    step_id=step_id,
                    idempotency_hash=idempotency_hash,
                )
                sink = SQLiteAuditSink(
                    connection,
                    reconciliation_connection_factory=self._database.connection,
                )
                self._events.start_tool_step(
                    run_id=run_id,
                    step_id=step_id,
                    ordinal=None,
                    invocation_id=invocation_id,
                    tool_name=_TOOL_NAME,
                    input_data={
                        "toolName": _TOOL_NAME,
                        "action": action,
                        "targetMutationId": mutation_id,
                        "idempotencyHash": idempotency_hash,
                    },
                )
                write_committed = False
                try:
                    result = await UndoExecutor(sink, default_undo_registry()).execute(
                        run_id=run_id,
                        step_id=step_id,
                        mutation_id=effective["id"],
                        invocation_id=invocation_id,
                        idempotency_key=idempotency_key,
                        cancellation_event=asyncio.Event(),
                    )
                    if isinstance(result, ToolReplayResult):
                        mutation_ids = result.mutation_ids
                        replayed = True
                        effective_invocation_id = result.invocation_id
                    else:
                        mutation_ids = tuple(
                            item["id"]
                            for item in repository.list_state_mutations(invocation_id)
                        )
                        replayed = False
                        effective_invocation_id = invocation_id
                    if len(mutation_ids) != 1:
                        raise RuntimeError(
                            "Mutation action did not persist exactly one inverse"
                        )
                    applied = repository.get_state_mutation(mutation_ids[0])
                    write_committed = True
                    self._complete_step_if_needed(
                        action=action,
                        run_id=run_id,
                        step_id=step_id,
                        invocation_id=effective_invocation_id,
                        target_mutation_id=mutation_id,
                        applied=applied,
                        replayed=replayed,
                    )
                    return self._result(
                        action=action,
                        run_id=run_id,
                        target_mutation_id=mutation_id,
                        invocation_id=effective_invocation_id,
                        applied=applied,
                        replayed=replayed,
                    )
                except asyncio.CancelledError:
                    self._finish_step_error(
                        run_id=run_id,
                        step_id=step_id,
                        status="cancelled",
                        error_code="cancelled",
                    )
                    raise
                except (InFlightInvocationError, TerminalInvocationError) as error:
                    if write_committed or self._invocation_succeeded(
                        repository, invocation_id
                    ):
                        raise
                    self._finish_step_error(
                        run_id=run_id,
                        step_id=step_id,
                        status="failed",
                        error_code="idempotency_conflict",
                    )
                    raise AgentUndoConflictError(
                        "idempotency_conflict",
                        "The idempotency key cannot be executed in its current state",
                    ) from error
                except (LookupError, PermissionError, ValueError) as error:
                    if write_committed or self._invocation_succeeded(
                        repository, invocation_id
                    ):
                        raise
                    self._finish_step_error(
                        run_id=run_id,
                        step_id=step_id,
                        status="failed",
                        error_code="undo_conflict",
                    )
                    raise AgentUndoConflictError(
                        "undo_conflict",
                        "The recorded mutation can no longer be applied safely",
                    ) from error
                except Exception:
                    if not write_committed and not self._invocation_succeeded(
                        repository, invocation_id
                    ):
                        self._finish_step_error(
                            run_id=run_id,
                            step_id=step_id,
                            status="failed",
                            error_code="undo_failed",
                        )
                    raise

    def recover_interrupted_actions(self) -> dict[str, int]:
        """Reconcile mutation actions left between their durable commit points."""

        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT s.id AS step_id, s.run_id, s.input_json,
                       i.id AS invocation_id, i.status AS invocation_status
                FROM agent_steps AS s
                JOIN agent_runs AS r ON r.id = s.run_id
                LEFT JOIN tool_invocations AS i ON i.step_id = s.id
                WHERE r.status IN ('completed', 'failed', 'cancelled', 'interrupted')
                  AND s.kind = 'tool' AND s.label = ?
                  AND s.status IN ('pending', 'running')
                ORDER BY s.run_id, s.ordinal, s.id
                """,
                (_TOOL_NAME,),
            ).fetchall()

        recovered = 0
        terminalized = 0
        for row in rows:
            if row["invocation_status"] == "succeeded":
                try:
                    (
                        action,
                        target_mutation_id,
                        idempotency_hash,
                    ) = self._recovery_step_input(str(row["input_json"]))
                    with self._database.connection() as connection:
                        repository = AgentRepository(connection)
                        invocation = repository.get_tool_invocation(
                            str(row["invocation_id"])
                        )
                        requested = self._mutation_for_run(
                            repository,
                            run_id=str(row["run_id"]),
                            mutation_id=target_mutation_id,
                        )
                        effective = self._effective_mutation(
                            repository,
                            requested=requested,
                            action=action,
                        )
                        mutations = repository.list_state_mutations(invocation["id"])
                    if len(mutations) != 1:
                        raise ValueError(
                            "succeeded mutation action must contain one inverse"
                        )
                    if (
                        invocation["run_id"] != row["run_id"]
                        or invocation["step_id"] != row["step_id"]
                        or invocation["tool_name"] != _TOOL_NAME
                        or invocation["permission_level"]
                        != int(PermissionLevel.LOCAL_REVERSIBLE)
                        or invocation["arguments"].get("mutation_id") != effective["id"]
                        or idempotency_hash
                        != self._idempotency_hash(
                            str(row["run_id"]), invocation["idempotency_key"]
                        )
                        or mutations[0]["run_id"] != row["run_id"]
                        or mutations[0]["tool_invocation_id"] != invocation["id"]
                    ):
                        raise PermissionError(
                            "succeeded mutation action recovery relationship is invalid"
                        )
                    self._complete_step_if_needed(
                        action=action,
                        run_id=str(row["run_id"]),
                        step_id=str(row["step_id"]),
                        invocation_id=str(row["invocation_id"]),
                        target_mutation_id=target_mutation_id,
                        applied=mutations[0],
                        replayed=True,
                    )
                    recovered += 1
                    continue
                except (LookupError, PermissionError, RuntimeError, ValueError):
                    pass
            self._terminalize_interrupted_action(
                run_id=str(row["run_id"]),
                step_id=str(row["step_id"]),
                invocation_id=(
                    str(row["invocation_id"])
                    if row["invocation_id"] is not None
                    else None
                ),
            )
            terminalized += 1
        return {"recovered": recovered, "terminalized": terminalized}

    @staticmethod
    def _recovery_step_input(value: str) -> tuple[UndoAction, str, str]:
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as error:
            raise ValueError("mutation action step input is invalid") from error
        if not isinstance(parsed, dict) or set(parsed) != {
            "toolName",
            "action",
            "targetMutationId",
            "idempotencyHash",
        }:
            raise ValueError("mutation action step input is invalid")
        action = parsed["action"]
        target_mutation_id = parsed["targetMutationId"]
        if (
            parsed["toolName"] != _TOOL_NAME
            or action not in {"undo", "redo"}
            or not isinstance(target_mutation_id, str)
            or len(target_mutation_id) > 128
            or not target_mutation_id
            or not isinstance(parsed["idempotencyHash"], str)
            or len(parsed["idempotencyHash"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in parsed["idempotencyHash"]
            )
        ):
            raise ValueError("mutation action step input is invalid")
        return action, target_mutation_id, parsed["idempotencyHash"]

    def _terminalize_interrupted_action(
        self,
        *,
        run_id: str,
        step_id: str,
        invocation_id: str | None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        event_digest = hashlib.sha256(
            f"{run_id}\0{step_id}\0mutation-action-interrupted".encode("utf-8")
        ).hexdigest()
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                if invocation_id is not None:
                    connection.execute(
                        """
                        UPDATE tool_invocations
                        SET status = 'cancelled', updated_at = ?, finished_at = ?,
                            error_code = 'process_restarted', error_detail = NULL
                        WHERE id = ? AND status IN ('pending', 'running')
                        """,
                        (now, now, invocation_id),
                    )
                connection.execute(
                    """
                    UPDATE agent_steps
                    SET status = 'failed', updated_at = ?, finished_at = ?,
                        error_code = 'process_restarted', error_detail = NULL
                    WHERE id = ? AND run_id = ? AND status IN ('pending', 'running')
                    """,
                    (now, now, step_id, run_id),
                )
                repository.append_event(
                    event_id=f"event-recovery-{event_digest}",
                    run_id=run_id,
                    event_type="warning",
                    payload={
                        "code": "mutation_action_interrupted",
                        "message": (
                            "A local mutation action was interrupted by restart; "
                            "refresh state and retry with a new idempotency key"
                        ),
                    },
                    commit=False,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _mutation_for_run(
        repository: AgentRepository, *, run_id: str, mutation_id: str
    ) -> dict:
        try:
            mutation = repository.get_state_mutation(mutation_id)
        except LookupError as error:
            raise AgentUndoNotFoundError(
                "Mutation was not found for this run"
            ) from error
        if mutation["run_id"] != run_id:
            raise AgentUndoNotFoundError("Mutation was not found for this run")
        return mutation

    @staticmethod
    def _effective_mutation(
        repository: AgentRepository, *, requested: dict, action: UndoAction
    ) -> dict:
        if action == "undo":
            return requested
        undo_invocation_id = requested["undone_by_tool_invocation_id"]
        if requested["undone_at"] is None or undo_invocation_id is None:
            raise AgentUndoConflictError(
                "mutation_not_undone",
                "The mutation must be undone before it can be redone",
            )
        inverses = repository.list_state_mutations(undo_invocation_id)
        if len(inverses) != 1:
            raise AgentUndoConflictError(
                "redo_unavailable", "The mutation has no valid recorded redo action"
            )
        inverse = inverses[0]
        if (
            inverse["run_id"] != requested["run_id"]
            or inverse["entity_type"] != requested["entity_type"]
            or inverse["entity_id"] != requested["entity_id"]
        ):
            raise AgentUndoForbiddenError("Recorded redo relationship is invalid")
        return inverse

    @staticmethod
    def _validate_actionable(mutation: dict) -> None:
        if mutation["entity_type"] != "study_task":
            raise AgentUndoForbiddenError(
                "Only recorded study-task mutations are enabled for this action"
            )
        if not mutation["reversible"] or mutation["undo"] is None:
            raise AgentUndoForbiddenError("Mutation is not reversibly recorded")
        if mutation["undone_at"] is not None:
            raise AgentUndoConflictError(
                "mutation_already_undone", "Mutation has already been undone"
            )

    @staticmethod
    def _validate_step_available(
        connection,
        *,
        run_id: str,
        step_id: str,
        idempotency_hash: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT id, status FROM agent_steps
            WHERE run_id = ? AND kind = 'tool' AND label = ?
              AND json_extract(input_json, '$.idempotencyHash') = ?
            """,
            (run_id, _TOOL_NAME, idempotency_hash),
        ).fetchone()
        if row is None:
            return
        if row["id"] != step_id:
            raise AgentUndoConflictError(
                "idempotency_key_reused",
                "The idempotency key was already used for different work",
            )
        if row["status"] in {"pending", "running"}:
            raise AgentUndoConflictError(
                "undo_in_progress", "This mutation action is already in progress"
            )
        raise AgentUndoConflictError(
            "idempotency_key_terminal",
            "This idempotency key belongs to an unsuccessful action; use a new key",
        )

    @staticmethod
    def _stable_ids(
        run_id: str,
        idempotency_key: str,
        *,
        action: UndoAction,
        target_mutation_id: str,
    ) -> tuple[str, str]:
        digest = hashlib.sha256(
            (
                f"{run_id}\0{idempotency_key}\0{action}\0"
                f"{target_mutation_id}\0undo-http-v1"
            ).encode("utf-8")
        ).hexdigest()
        return f"inv-undo-{digest}", f"step-undo-{digest}"

    @staticmethod
    def _idempotency_hash(run_id: str, idempotency_key: str) -> str:
        return hashlib.sha256(
            f"{run_id}\0{idempotency_key}\0undo-http-key-v1".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_existing_invocation(
        invocation: dict, *, step_id: str, arguments_hash: str
    ) -> None:
        expected = (
            step_id,
            _TOOL_NAME,
            int(PermissionLevel.LOCAL_REVERSIBLE),
            arguments_hash,
        )
        actual = tuple(
            invocation[key]
            for key in (
                "step_id",
                "tool_name",
                "permission_level",
                "arguments_hash",
            )
        )
        if actual != expected:
            raise AgentUndoConflictError(
                "idempotency_key_reused",
                "The idempotency key was already used for different work",
            )

    @staticmethod
    def _invocation_succeeded(repository: AgentRepository, invocation_id: str) -> bool:
        try:
            return (
                repository.get_tool_invocation(invocation_id)["status"] == "succeeded"
            )
        except LookupError:
            return False

    def _complete_step_if_needed(
        self,
        *,
        action: UndoAction,
        run_id: str,
        step_id: str,
        invocation_id: str,
        target_mutation_id: str,
        applied: dict,
        replayed: bool,
    ) -> None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT status FROM agent_steps WHERE id = ? AND run_id = ?",
                (step_id, run_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("Mutation action step is missing")
        if row["status"] == "completed":
            return
        if row["status"] in {"failed", "cancelled", "interrupted"}:
            raise AgentUndoConflictError(
                "idempotency_key_terminal",
                "This idempotency key belongs to an unsuccessful action; use a new key",
            )
        self._events.complete_tool_step(
            run_id=run_id,
            step_id=step_id,
            result_payload={
                "invocationId": invocation_id,
                "toolName": _TOOL_NAME,
                "action": action,
                "targetMutationId": target_mutation_id,
                "mutationId": applied["id"],
                "replayed": replayed,
            },
            mutation_payloads=[
                {
                    "invocationId": invocation_id,
                    "mutationId": applied["id"],
                    "entityType": applied["entity_type"],
                    "entityId": applied["entity_id"],
                    "operation": applied["operation"],
                    "reversible": True,
                    "action": action,
                    "targetMutationId": target_mutation_id,
                    "replayed": replayed,
                }
            ],
        )

    def _finish_step_error(
        self,
        *,
        run_id: str,
        step_id: str,
        status: Literal["failed", "cancelled"],
        error_code: str,
    ) -> None:
        try:
            self._events.finish_tool_step_error(
                run_id=run_id,
                step_id=step_id,
                status=status,
                error_code=error_code,
            )
        except (LookupError, ValueError):
            pass

    @staticmethod
    def _result(
        *,
        action: UndoAction,
        run_id: str,
        target_mutation_id: str,
        invocation_id: str,
        applied: dict,
        replayed: bool,
    ) -> AgentUndoResult:
        return AgentUndoResult(
            action=action,
            run_id=run_id,
            target_mutation_id=target_mutation_id,
            invocation_id=invocation_id,
            mutation_id=applied["id"],
            entity_type=applied["entity_type"],
            entity_id=applied["entity_id"],
            operation=applied["operation"],
            replayed=replayed,
        )


__all__ = [
    "AgentUndoConflictError",
    "AgentUndoForbiddenError",
    "AgentUndoNotFoundError",
    "AgentUndoResult",
    "AgentUndoService",
    "UndoAction",
]
