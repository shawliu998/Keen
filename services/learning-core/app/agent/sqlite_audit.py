from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager, asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from app.repositories.agent_repository import AgentRepository, MutationInput

from .audit import (
    AuditSink,
    ToolAuditReservation,
    ToolAuditStart,
    ToolAuditSuccess,
    ToolAuditTerminal,
)
from .types import PermissionLevel, StateMutation
from .transaction import SQLiteToolSession


class InFlightInvocationError(RuntimeError):
    """The idempotency key belongs to work whose outcome is not yet durable."""


class TerminalInvocationError(RuntimeError):
    """A failed/cancelled/denied invocation cannot be silently re-executed."""


def mutation_id_for_invocation(invocation_id: str, ordinal: int) -> str:
    """Return the stable public identity shared by audit and event adapters."""

    if ordinal < 0:
        raise ValueError("mutation ordinal must be non-negative")
    digest = hashlib.sha256(f"{invocation_id}:{ordinal}".encode()).hexdigest()
    return f"mutation-{digest}"


class SQLiteAuditSink(AuditSink):
    """SQLite-backed invocation audit and transaction coordinator.

    One sink owns one request-scoped SQLite connection. Level 2 tools must use
    ``transaction`` as the executor's transaction factory so the domain write,
    successful invocation row and raw typed undo records share one commit.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        reconciliation_connection_factory: (
            Callable[[], AbstractContextManager[sqlite3.Connection]] | None
        ) = None,
    ) -> None:
        self.connection = connection
        self.repository = AgentRepository(connection)
        self._reconciliation_connection_factory = reconciliation_connection_factory
        self._commit_candidate_invocation_id: str | None = None
        self._session_owner_token = object()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SQLiteToolSession]:
        if self.connection.in_transaction:
            raise RuntimeError("agent transaction cannot be nested")
        self._commit_candidate_invocation_id = None
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield SQLiteToolSession(self.connection, self._session_owner_token)
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        else:
            try:
                self.connection.commit()
            except BaseException:
                if self.connection.in_transaction:
                    self.connection.rollback()
                    raise
                candidate = self._commit_candidate_invocation_id
                if candidate is not None and self._is_durably_succeeded(candidate):
                    return
                raise
        finally:
            self._commit_candidate_invocation_id = None

    def _is_durably_succeeded(self, invocation_id: str) -> bool:
        """Reconcile a driver error that may have happened after COMMIT applied."""

        try:
            with self._reconciliation_connection() as connection:
                invocation = AgentRepository(connection).get_tool_invocation(
                    invocation_id
                )
        except (LookupError, RuntimeError, sqlite3.Error):
            return False
        return invocation["status"] == "succeeded"

    @contextmanager
    def _reconciliation_connection(self) -> Iterator[sqlite3.Connection]:
        if self._reconciliation_connection_factory is not None:
            with self._reconciliation_connection_factory() as connection:
                yield connection
            return
        database_path = ""
        try:
            database_rows = self.connection.execute("PRAGMA database_list").fetchall()
            database_path = next(
                (str(row[2]) for row in database_rows if row[1] == "main"), ""
            )
        except sqlite3.Error:
            database_path = ""
        if not database_path:
            yield self.connection
            return
        connection = sqlite3.connect(database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    async def record_started(self, record: ToolAuditStart) -> ToolAuditReservation:
        try:
            reservation = self.repository.reserve_tool_invocation(
                invocation_id=record.invocation_id,
                run_id=record.run_id,
                step_id=record.step_id,
                tool_name=record.tool_name,
                permission_level=int(record.permission_level),
                arguments_summary=record.arguments.summary,
                arguments_hash=record.arguments.sha256,
                idempotency_key=record.idempotency_key,
            )
        except (LookupError, PermissionError, ValueError):
            raise
        except Exception as commit_error:
            if self.connection.in_transaction:
                self.connection.rollback()
                raise
            durable = self._find_durable_reservation(record)
            if durable is None:
                raise
            if (
                durable["id"] == record.invocation_id
                and durable["status"] in {"pending", "running"}
                and self._fail_uncertain_reservation(durable["id"])
            ):
                raise TerminalInvocationError(
                    "tool reservation committed but execution did not start; "
                    "the invocation was durably failed and requires a new idempotency key"
                ) from commit_error
            try:
                return self._reservation_for_invocation(durable)
            except (InFlightInvocationError, TerminalInvocationError) as error:
                raise error from commit_error
        invocation = reservation["invocation"]
        if reservation["created"]:
            return ToolAuditReservation(
                disposition="execute",
                invocation_id=invocation["id"],
            )
        return self._reservation_for_invocation(invocation)

    def _find_durable_reservation(self, record: ToolAuditStart) -> dict | None:
        try:
            with self._reconciliation_connection() as connection:
                invocation = AgentRepository(connection).find_tool_invocation(
                    run_id=record.run_id,
                    idempotency_key=record.idempotency_key,
                )
        except (RuntimeError, sqlite3.Error):
            return None
        if invocation is None:
            return None
        expected = (
            record.step_id,
            record.tool_name,
            int(record.permission_level),
            record.arguments.sha256,
        )
        actual = tuple(
            invocation[key]
            for key in ("step_id", "tool_name", "permission_level", "arguments_hash")
        )
        if actual != expected:
            raise ValueError(
                "idempotency key was durably claimed with a different tool payload"
            )
        return invocation

    def _fail_uncertain_reservation(self, invocation_id: str) -> bool:
        try:
            with self._reconciliation_connection() as connection:
                invocation = AgentRepository(connection).finish_tool_invocation(
                    invocation_id,
                    status="failed",
                    error_code="reservation_commit_uncertain",
                )
        except (LookupError, RuntimeError, ValueError, sqlite3.Error):
            return False
        return invocation["status"] == "failed"

    def _reservation_for_invocation(self, invocation: dict) -> ToolAuditReservation:
        status = invocation["status"]
        if status == "succeeded":
            with self._reconciliation_connection() as connection:
                mutations = AgentRepository(connection).list_state_mutations(
                    invocation["id"]
                )
            result_summary = invocation["result_summary"]
            if not isinstance(result_summary, dict):
                raise RuntimeError("completed invocation is missing its result summary")
            return ToolAuditReservation(
                disposition="replay",
                invocation_id=invocation["id"],
                result_summary=result_summary,
                mutation_ids=tuple(item["id"] for item in mutations),
            )
        if status in {"pending", "running"}:
            raise InFlightInvocationError(
                "tool invocation is already in flight; retry only after recovery resolves it"
            )
        raise TerminalInvocationError(
            f"tool invocation already ended with status {status}; use a new idempotency key"
        )

    async def record_succeeded(
        self,
        record: ToolAuditSuccess,
        *,
        mutations: tuple[StateMutation, ...],
        transaction: object | None,
    ) -> None:
        invocation = self.repository.get_tool_invocation(record.invocation_id)
        permission = PermissionLevel(invocation["permission_level"])
        if permission is PermissionLevel.LOCAL_REVERSIBLE:
            if (
                not isinstance(transaction, SQLiteToolSession)
                or not transaction._belongs_to(
                    self.connection, self._session_owner_token
                )
                or not self.connection.in_transaction
            ):
                raise RuntimeError(
                    "Level 2 success audit must join the sink's active SQLite transaction"
                )
            commit = False
        else:
            if transaction is not None:
                raise RuntimeError(
                    "Level 1 success audit cannot join a write transaction"
                )
            commit = True
        inputs: list[MutationInput] = []
        for ordinal, mutation in enumerate(mutations):
            inputs.append(
                {
                    "id": mutation_id_for_invocation(record.invocation_id, ordinal),
                    "entity_type": mutation.entity_type,
                    "entity_id": mutation.entity_id,
                    "operation": mutation.operation,
                    "before": mutation.before,
                    "after": mutation.after,
                    "undo": mutation.undo.model_dump(mode="json"),
                    "reversible": True,
                }
            )
        self.repository.complete_tool_invocation(
            record.invocation_id,
            result_summary=record.result.summary,
            mutations=inputs,
            commit=commit,
        )
        if permission is PermissionLevel.LOCAL_REVERSIBLE:
            self._commit_candidate_invocation_id = record.invocation_id

    async def record_failed(self, record: ToolAuditTerminal) -> None:
        self.repository.finish_tool_invocation(
            record.invocation_id,
            status="failed",
            error_code=record.error_code,
        )

    async def record_cancelled(self, record: ToolAuditTerminal) -> None:
        self.repository.finish_tool_invocation(
            record.invocation_id,
            status="cancelled",
            error_code=record.error_code,
        )

    async def record_rejected(self, record: ToolAuditTerminal) -> None:
        self.repository.finish_tool_invocation(
            record.invocation_id,
            status="denied",
            error_code=record.error_code,
        )
