from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..database import Database
from ..repositories import JsonValue
from ..repositories.agent_repository import AgentRepository
from .types import is_hidden_reasoning_key, validate_bounded_json_object

AgentEventType = Literal[
    "metadata",
    "status",
    "tool_start",
    "tool_result",
    "content_delta",
    "checkpoint",
    "state_mutation",
    "warning",
    "done",
    "error",
]
_TERMINAL_EVENT_TYPES = {"done", "error"}
_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


def _reject_hidden_reasoning(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if is_hidden_reasoning_key(key):
                raise ValueError("agent events must not contain hidden reasoning")
            _reject_hidden_reasoning(child)
    elif isinstance(value, list):
        for child in value:
            _reject_hidden_reasoning(child)


class DurableAgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    run_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    sequence: int = Field(ge=0)
    event_type: AgentEventType
    payload: dict[str, object]
    created_at: str = Field(min_length=1, max_length=64)

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, object]) -> dict[str, object]:
        validate_bounded_json_object(value)
        _reject_hidden_reasoning(value)
        return value


def encode_sse(event: DurableAgentEvent) -> str:
    data = json.dumps(
        event.payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"id: {event.id}\nevent: {event.event_type}\ndata: {data}\n\n"


class AgentEventStore:
    """Adapter that keeps SQLite events as the only replay source of truth."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get_run(self, run_id: str) -> dict | None:
        self._validate_identifier(run_id, label="run ID")
        with self._database.connection() as connection:
            return AgentRepository(connection).get_run(run_id)

    def start_run(
        self, run_id: str, *, metadata: dict[str, object]
    ) -> list[DurableAgentEvent]:
        self._validate_identifier(run_id, label="run ID")
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                run = repository.get_run(run_id)
                if run is None:
                    raise LookupError("agent run not found")
                if run["status"] != "queued":
                    raise ValueError("only a queued Agent run can start")
                rows = [
                    repository.append_event(
                        event_id=self._new_event_id(),
                        run_id=run_id,
                        event_type="metadata",
                        payload=self._payload(metadata),
                        commit=False,
                    )
                ]
                repository.transition_run(run_id, status="running", commit=False)
                rows.append(
                    repository.append_event(
                        event_id=self._new_event_id(),
                        run_id=run_id,
                        event_type="status",
                        payload={"status": "running"},
                        commit=False,
                    )
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return [self._event(row) for row in rows]

    def start_tool_step(
        self,
        *,
        run_id: str,
        step_id: str,
        ordinal: int,
        invocation_id: str,
        tool_name: str,
    ) -> DurableAgentEvent:
        self._validate_identifier(run_id, label="run ID")
        self._validate_identifier(step_id, label="step ID")
        now = datetime.now(UTC).isoformat()
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT run_id, ordinal, kind, status, label FROM agent_steps WHERE id = ?",
                    (step_id,),
                ).fetchone()
                if existing is None:
                    repository.add_step(
                        step_id=step_id,
                        run_id=run_id,
                        ordinal=ordinal,
                        kind="tool",
                        label=tool_name,
                        input_data={"toolName": tool_name},
                        commit=False,
                    )
                    connection.execute(
                        """
                        UPDATE agent_steps
                        SET status = 'running', updated_at = ?, started_at = ?
                        WHERE id = ?
                        """,
                        (now, now, step_id),
                    )
                    replay_candidate = False
                else:
                    expected = (run_id, "tool", tool_name)
                    actual = (existing["run_id"], existing["kind"], existing["label"])
                    if actual != expected:
                        raise ValueError(
                            "stable Agent step ID was reused inconsistently"
                        )
                    replay_candidate = existing["status"] == "completed"
                    if not replay_candidate:
                        raise RuntimeError("Agent tool step is already in flight")
                row = repository.append_event(
                    event_id=self._new_event_id(),
                    run_id=run_id,
                    event_type="tool_start",
                    payload={
                        "invocationId": invocation_id,
                        "toolName": tool_name,
                        "replayCandidate": replay_candidate,
                    },
                    commit=False,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self._event(row)

    def complete_tool_step(
        self,
        *,
        run_id: str,
        step_id: str,
        result_payload: dict[str, object],
        mutation_payloads: list[dict[str, object]],
    ) -> list[DurableAgentEvent]:
        safe_result = self._payload(result_payload)
        safe_mutations = [self._payload(payload) for payload in mutation_payloads]
        now = datetime.now(UTC).isoformat()
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                step = connection.execute(
                    "SELECT run_id, status FROM agent_steps WHERE id = ?", (step_id,)
                ).fetchone()
                if step is None or step["run_id"] != run_id:
                    raise LookupError("Agent tool step not found for run")
                if step["status"] == "running":
                    connection.execute(
                        """
                        UPDATE agent_steps
                        SET status = 'completed', output_json = ?, updated_at = ?,
                            finished_at = ?
                        WHERE id = ?
                        """,
                        (
                            json.dumps(
                                safe_result,
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                            now,
                            now,
                            step_id,
                        ),
                    )
                elif step["status"] != "completed":
                    raise ValueError(
                        "Agent tool step cannot complete from its current state"
                    )
                rows = [
                    repository.append_event(
                        event_id=self._new_event_id(),
                        run_id=run_id,
                        event_type="tool_result",
                        payload=safe_result,
                        commit=False,
                    )
                ]
                rows.extend(
                    repository.append_event(
                        event_id=self._new_event_id(),
                        run_id=run_id,
                        event_type="state_mutation",
                        payload=payload,
                        commit=False,
                    )
                    for payload in safe_mutations
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return [self._event(row) for row in rows]

    def finish_tool_step_error(
        self,
        *,
        run_id: str,
        step_id: str,
        status: Literal["failed", "cancelled"],
        error_code: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    UPDATE agent_steps
                    SET status = ?, error_code = ?, updated_at = ?, finished_at = ?
                    WHERE id = ? AND run_id = ? AND status IN ('pending', 'running')
                    """,
                    (status, error_code, now, now, step_id, run_id),
                )
                if cursor.rowcount != 1:
                    step = connection.execute(
                        "SELECT status FROM agent_steps WHERE id = ? AND run_id = ?",
                        (step_id, run_id),
                    ).fetchone()
                    if step is None:
                        raise LookupError("Agent tool step not found for run")
                    if step["status"] != "completed":
                        raise ValueError(
                            "Agent tool step cannot fail from its current state"
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def append(
        self,
        run_id: str,
        event_type: AgentEventType,
        payload: dict[str, object],
    ) -> DurableAgentEvent:
        self._validate_identifier(run_id, label="run ID")
        safe_payload = self._payload(payload)
        with self._database.connection() as connection:
            row = AgentRepository(connection).append_event(
                event_id=self._new_event_id(),
                run_id=run_id,
                event_type=event_type,
                payload=safe_payload,
            )
        return self._event(row)

    def finish_run(
        self,
        run_id: str,
        *,
        status: Literal["completed", "failed", "cancelled"],
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> list[DurableAgentEvent]:
        self._validate_identifier(run_id, label="run ID")
        if status == "completed" and (
            error_code is not None or error_detail is not None
        ):
            raise ValueError("completed runs cannot carry errors")
        if status != "completed" and not error_code:
            raise ValueError("failed or cancelled runs require an error code")
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                run = repository.get_run(run_id)
                if run is None:
                    raise LookupError("agent run not found")
                if run["status"] in _TERMINAL_RUN_STATUSES:
                    connection.rollback()
                    return []
                repository.transition_run(
                    run_id,
                    status=status,
                    error_code=error_code,
                    error_detail=error_detail,
                    commit=False,
                )
                rows = [
                    repository.append_event(
                        event_id=self._new_event_id(),
                        run_id=run_id,
                        event_type="status",
                        payload={"status": status},
                        commit=False,
                    )
                ]
                if status == "completed":
                    rows.append(
                        repository.append_event(
                            event_id=self._new_event_id(),
                            run_id=run_id,
                            event_type="done",
                            payload={"status": "completed"},
                            commit=False,
                        )
                    )
                else:
                    error_payload: dict[str, object] = {
                        "code": error_code,
                        "retryable": status == "failed",
                        "status": status,
                    }
                    if error_detail:
                        error_payload["message"] = error_detail
                    rows.append(
                        repository.append_event(
                            event_id=self._new_event_id(),
                            run_id=run_id,
                            event_type="error",
                            payload=self._payload(error_payload),
                            commit=False,
                        )
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return [self._event(row) for row in rows]

    def list_events(
        self, run_id: str, *, after_sequence: int = -1
    ) -> list[DurableAgentEvent]:
        self._validate_identifier(run_id, label="run ID")
        with self._database.connection() as connection:
            repository = AgentRepository(connection)
            if repository.get_run(run_id) is None:
                raise LookupError("agent run not found")
            return [
                self._event(row)
                for row in repository.list_events(run_id, after_sequence=after_sequence)
            ]

    def sequence_after_last_event_id(
        self, run_id: str, last_event_id: str | None
    ) -> int:
        if last_event_id is None or not last_event_id.strip():
            return -1
        self._validate_identifier(run_id, label="run ID")
        self._validate_identifier(last_event_id, label="Last-Event-ID")
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT run_id, sequence FROM agent_events WHERE id = ?",
                (last_event_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Last-Event-ID does not identify a durable Agent event")
        if row["run_id"] != run_id:
            raise ValueError("Last-Event-ID belongs to a different Agent run")
        return int(row["sequence"])

    @staticmethod
    def _new_event_id() -> str:
        return f"event-{uuid.uuid4().hex}"

    @staticmethod
    def _validate_identifier(value: str, *, label: str) -> None:
        try:
            DurableAgentEvent(
                id=value,
                run_id=value,
                sequence=0,
                event_type="metadata",
                payload={},
                created_at="validation",
            )
        except ValueError as error:
            raise ValueError(f"invalid {label}") from error

    @staticmethod
    def _payload(payload: dict[str, object]) -> dict[str, JsonValue]:
        event = DurableAgentEvent(
            id="validation",
            run_id="validation",
            sequence=0,
            event_type="metadata",
            payload=payload,
            created_at="validation",
        )
        return event.payload  # type: ignore[return-value]

    @staticmethod
    def _event(row: dict) -> DurableAgentEvent:
        return DurableAgentEvent(
            id=row["id"],
            run_id=row["run_id"],
            sequence=row["sequence"],
            event_type=row["event_type"],
            payload=row["payload"],
            created_at=row["created_at"],
        )


class DurableEventStream:
    def __init__(self, store: AgentEventStore, *, poll_interval: float = 0.05) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self._store = store
        self._poll_interval = poll_interval

    async def replay(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        disconnected: asyncio.Event | None = None,
    ) -> AsyncIterator[DurableAgentEvent]:
        after_sequence = self._store.sequence_after_last_event_id(run_id, last_event_id)
        while True:
            events = self._store.list_events(run_id, after_sequence=after_sequence)
            for event in events:
                after_sequence = event.sequence
                yield event
                if event.event_type in _TERMINAL_EVENT_TYPES:
                    return
            run = self._store.get_run(run_id)
            if run is None:
                raise LookupError("agent run not found")
            if run["status"] in _TERMINAL_RUN_STATUSES:
                return
            if disconnected is not None and disconnected.is_set():
                return
            if disconnected is None:
                await asyncio.sleep(self._poll_interval)
            else:
                try:
                    await asyncio.wait_for(disconnected.wait(), self._poll_interval)
                except TimeoutError:
                    pass


__all__ = [
    "AgentEventStore",
    "AgentEventType",
    "DurableAgentEvent",
    "DurableEventStream",
    "encode_sse",
]
