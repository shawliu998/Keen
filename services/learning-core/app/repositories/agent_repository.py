from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from . import JsonValue, dump_json, load_json, validate_json, write_scope


class MutationInput(TypedDict):
    id: str
    entity_type: str
    entity_id: str
    operation: str
    before: NotRequired[JsonValue]
    after: NotRequired[JsonValue]
    undo: NotRequired[JsonValue]
    reversible: NotRequired[bool]


class ToolReservation(TypedDict):
    invocation: dict
    created: bool


_RUN_TRANSITIONS = {
    "queued": frozenset({"running", "failed", "cancelled", "interrupted"}),
    "running": frozenset(
        {"waiting_approval", "completed", "failed", "cancelled", "interrupted"}
    ),
    "waiting_approval": frozenset({"running", "failed", "cancelled", "interrupted"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _recovery_event_id(run_id: str, event_type: str) -> str:
    digest = hashlib.sha256(f"{run_id}\0{event_type}".encode("utf-8")).hexdigest()
    return f"event-recovery-{digest}"


def _object_json(value: object, *, label: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return dump_json(value)


_SENSITIVE_AUDIT_KEYS = {
    "analysis",
    "answer",
    "api_key",
    "body",
    "chunks",
    "content",
    "chain_of_thought",
    "document",
    "document_text",
    "full_text",
    "hidden_reasoning",
    "internal_reasoning",
    "password",
    "path",
    "private_data",
    "prompt",
    "reasoning",
    "reasoning_trace",
    "scratchpad",
    "secret",
    "source_content",
    "text",
    "token",
    "thoughts",
}
_SENSITIVE_AUDIT_COMPACT_KEYS = {key.replace("_", "") for key in _SENSITIVE_AUDIT_KEYS}
_SENSITIVE_AUDIT_SUFFIXES = (
    "_answer",
    "_body",
    "_content",
    "_password",
    "_path",
    "_prompt",
    "_secret",
    "_text",
    "_token",
)
_SAFE_AUDIT_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SAFE_AUDIT_ENUM_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_AUDIT_TEXT_KEYS = {
    "effect",
    "entity_type",
    "format",
    "kind",
    "mode",
    "operation",
    "status",
    "tool_name",
    "type",
}
_CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALPHANUMERIC_RE = re.compile(r"[^A-Za-z0-9]+")


def _canonical_audit_key(key: str) -> str:
    with_boundaries = _CAMEL_CASE_BOUNDARY_RE.sub("_", key)
    return _NON_ALPHANUMERIC_RE.sub("_", with_boundaries).strip("_").lower()


def _is_sensitive_audit_key(key: str) -> bool:
    canonical = _canonical_audit_key(key)
    compact = canonical.replace("_", "")
    return (
        canonical in _SENSITIVE_AUDIT_KEYS
        or compact in _SENSITIVE_AUDIT_COMPACT_KEYS
        or canonical.endswith(_SENSITIVE_AUDIT_SUFFIXES)
    )


def _redact_audit_value(value: JsonValue, *, key: str = "") -> JsonValue:
    canonical = _canonical_audit_key(key)
    is_identifier = canonical.endswith("_id") or canonical.endswith("_ids")
    if not is_identifier and _is_sensitive_audit_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            child_key: _redact_audit_value(child, key=child_key)
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        child_key = canonical[:-1] if canonical.endswith("_ids") else ""
        return [_redact_audit_value(child, key=child_key) for child in value]
    if isinstance(value, str) and is_identifier:
        if _SAFE_AUDIT_IDENTIFIER_RE.fullmatch(value) is None:
            return "[REDACTED:INVALID_ID]"
        return value
    if isinstance(value, str):
        if canonical in _SAFE_AUDIT_TEXT_KEYS and _SAFE_AUDIT_ENUM_RE.fullmatch(value):
            return value
        return "[REDACTED:TEXT]"
    return value


def _audit_object(value: object, *, label: str) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    validated = validate_json(value)
    if not isinstance(validated, dict):  # pragma: no cover - guarded above
        raise ValueError(f"{label} must be an object")
    canonical = dump_json(validated)
    redacted = dump_json(_redact_audit_value(validated))
    if len(redacted) > 10_000:
        raise ValueError(f"{label} is too large for audit storage")
    return redacted, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AgentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_run(
        self,
        *,
        run_id: str,
        kind: str,
        provider: str,
        model: str,
        user_intent: str,
        mode: str,
        prompt_version: str,
        input_data: dict[str, JsonValue],
        idempotency_key: str,
        conversation_id: str | None = None,
        study_session_id: str | None = None,
        commit: bool = True,
    ) -> dict:
        if kind not in {"conversation", "deep_learn", "assessment", "review"}:
            raise ValueError("invalid agent run kind")
        if mode not in {"ask", "teach", "study", "review", "plan"}:
            raise ValueError("invalid agent run mode")
        now = _now()
        with write_scope(self.connection, commit=commit):
            if conversation_id is not None and study_session_id is not None:
                context = self.connection.execute(
                    """
                    SELECT s.conversation_id AS session_conversation_id,
                           s.course_id AS session_course_id,
                           c.course_id AS conversation_course_id
                    FROM study_sessions s JOIN conversations c ON c.id = ?
                    WHERE s.id = ?
                    """,
                    (conversation_id, study_session_id),
                ).fetchone()
                if (
                    context is None
                    or context["session_conversation_id"] != conversation_id
                    or context["conversation_course_id"]
                    not in {None, context["session_course_id"]}
                ):
                    raise ValueError(
                        "agent run conversation and study session do not match"
                    )
            existing = self.connection.execute(
                "SELECT id, conversation_id, study_session_id, kind, user_intent, mode, provider, model, prompt_version, input_json FROM agent_runs WHERE kind = ? AND idempotency_key = ?",
                (kind, idempotency_key),
            ).fetchone()
            serialized_input = _object_json(input_data, label="run input")
            if existing is not None:
                expected = (
                    conversation_id,
                    study_session_id,
                    kind,
                    user_intent,
                    mode,
                    provider,
                    model,
                    prompt_version,
                    serialized_input,
                )
                actual = tuple(
                    existing[key]
                    for key in (
                        "conversation_id",
                        "study_session_id",
                        "kind",
                        "user_intent",
                        "mode",
                        "provider",
                        "model",
                        "prompt_version",
                        "input_json",
                    )
                )
                if actual != expected:
                    raise ValueError(
                        "idempotency key was reused with a different run payload"
                    )
                replay = self.get_run(existing["id"])
                if replay is None:  # pragma: no cover
                    raise RuntimeError("idempotent run disappeared")
                return replay
            self.connection.execute(
                """
                INSERT INTO agent_runs
                    (id, conversation_id, study_session_id, kind, user_intent,
                     mode, status, provider, model, prompt_version, input_json,
                     error_code, error_detail, idempotency_key, created_at,
                     updated_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL)
                """,
                (
                    run_id,
                    conversation_id,
                    study_session_id,
                    kind,
                    user_intent,
                    mode,
                    provider,
                    model,
                    prompt_version,
                    serialized_input,
                    idempotency_key,
                    now,
                    now,
                ),
            )
        run = self.get_run(run_id)
        if run is None:  # pragma: no cover
            raise RuntimeError("agent run insert did not persist")
        return run

    def get_run(self, run_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, conversation_id, study_session_id, kind, user_intent,
                   mode, status, provider, model, prompt_version, input_json,
                   error_code, error_detail, idempotency_key,
                   created_at, updated_at, started_at, finished_at
            FROM agent_runs WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["input"] = load_json(result.pop("input_json"))
        return result

    def find_run_by_idempotency(
        self, *, kind: str, idempotency_key: str
    ) -> dict | None:
        row = self.connection.execute(
            "SELECT id FROM agent_runs WHERE kind = ? AND idempotency_key = ?",
            (kind, idempotency_key),
        ).fetchone()
        return self.get_run(str(row["id"])) if row is not None else None

    def transition_run(
        self,
        run_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_detail: str | None = None,
        commit: bool = True,
    ) -> dict:
        current = self.get_run(run_id)
        if current is None:
            raise LookupError("agent run not found")
        if status not in _RUN_TRANSITIONS[current["status"]]:
            raise ValueError(f"invalid run transition: {current['status']} -> {status}")
        now = _now()
        terminal = status in {"completed", "failed", "cancelled", "interrupted"}
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                UPDATE agent_runs
                SET status = ?, error_code = ?, error_detail = ?, updated_at = ?,
                    started_at = CASE WHEN ? = 'running' AND started_at IS NULL THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? THEN ? ELSE NULL END
                WHERE id = ?
                """,
                (
                    status,
                    error_code,
                    error_detail,
                    now,
                    status,
                    now,
                    terminal,
                    now,
                    run_id,
                ),
            )
        result = self.get_run(run_id)
        if result is None:  # pragma: no cover
            raise RuntimeError("agent run disappeared")
        return result

    def add_step(
        self,
        *,
        step_id: str,
        run_id: str,
        ordinal: int,
        kind: str,
        label: str,
        input_data: dict[str, JsonValue],
        commit: bool = True,
    ) -> dict:
        if kind not in {"model", "tool", "checkpoint", "approval"}:
            raise ValueError("invalid agent step kind")
        now = _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO agent_steps
                    (id, run_id, ordinal, kind, status, label, input_json,
                     output_json, error_code, error_detail, created_at, updated_at,
                     started_at, finished_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, NULL, NULL, NULL, ?, ?, NULL, NULL)
                """,
                (
                    step_id,
                    run_id,
                    ordinal,
                    kind,
                    label,
                    _object_json(input_data, label="step input"),
                    now,
                    now,
                ),
            )
        return self._get_json_row("agent_steps", step_id, ("input_json", "output_json"))

    def append_event(
        self,
        *,
        event_id: str,
        run_id: str,
        event_type: str,
        payload: JsonValue,
        commit: bool = True,
    ) -> dict:
        allowed = {
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
        }
        if event_type not in allowed:
            raise ValueError("invalid agent event type")
        now = _now()
        with write_scope(self.connection, commit=commit):
            sequence = int(
                self.connection.execute(
                    "SELECT COALESCE(MAX(sequence), -1) + 1 FROM agent_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            )
            self.connection.execute(
                """
                INSERT INTO agent_events (id, run_id, sequence, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, run_id, sequence, event_type, dump_json(payload), now),
            )
        return {
            "id": event_id,
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "payload": load_json(dump_json(payload)),
            "created_at": now,
        }

    def list_events(self, run_id: str, *, after_sequence: int = -1) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, run_id, sequence, event_type, payload_json, created_at
            FROM agent_events WHERE run_id = ? AND sequence > ? ORDER BY sequence
            """,
            (run_id, after_sequence),
        ).fetchall()
        return [
            {
                **{key: row[key] for key in row.keys() if key != "payload_json"},
                "payload": load_json(row["payload_json"]),
            }
            for row in rows
        ]

    def start_tool_invocation(
        self,
        *,
        invocation_id: str,
        run_id: str,
        tool_name: str,
        permission_level: int,
        arguments: dict[str, JsonValue],
        idempotency_key: str,
        step_id: str | None = None,
        commit: bool = True,
    ) -> dict:
        if permission_level not in {1, 2, 3}:
            raise ValueError("invalid permission level")
        serialized_arguments, arguments_hash = _audit_object(
            arguments, label="tool arguments"
        )
        reservation = self.reserve_tool_invocation(
            invocation_id=invocation_id,
            run_id=run_id,
            tool_name=tool_name,
            permission_level=permission_level,
            arguments_summary=load_json(serialized_arguments),
            arguments_hash=arguments_hash,
            idempotency_key=idempotency_key,
            step_id=step_id,
            commit=commit,
        )
        return reservation["invocation"]

    def reserve_tool_invocation(
        self,
        *,
        invocation_id: str,
        run_id: str,
        tool_name: str,
        permission_level: int,
        arguments_summary: dict[str, JsonValue],
        arguments_hash: str,
        idempotency_key: str,
        step_id: str | None = None,
        commit: bool = True,
    ) -> ToolReservation:
        """Atomically claim an invocation idempotency key.

        The caller supplies a bounded redacted summary plus the SHA-256 of the
        original validated arguments. The hash, rather than the redacted form,
        distinguishes payloads that redact to the same value.
        """

        if permission_level not in {1, 2, 3}:
            raise ValueError("invalid permission level")
        if len(arguments_hash) != 64 or any(
            character not in "0123456789abcdef" for character in arguments_hash
        ):
            raise ValueError("arguments hash must be lowercase SHA-256")
        serialized_arguments = _audit_object(
            arguments_summary, label="tool argument summary"
        )[0]
        now = _now()
        with write_scope(self.connection, commit=commit):
            existing = self.connection.execute(
                "SELECT * FROM tool_invocations WHERE run_id = ? AND idempotency_key = ?",
                (run_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                expected = (step_id, tool_name, permission_level, arguments_hash)
                actual = tuple(
                    existing[key]
                    for key in (
                        "step_id",
                        "tool_name",
                        "permission_level",
                        "arguments_hash",
                    )
                )
                if actual != expected:
                    raise ValueError(
                        "idempotency key was reused with different tool arguments"
                    )
                return {
                    "invocation": self.get_tool_invocation(existing["id"]),
                    "created": False,
                }
            self.connection.execute(
                """
                INSERT INTO tool_invocations
                    (id, run_id, step_id, tool_name, permission_level, status,
                     arguments_json, arguments_hash, result_summary_json, error_code, error_detail,
                     idempotency_key, created_at, updated_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, 'running', ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, NULL)
                """,
                (
                    invocation_id,
                    run_id,
                    step_id,
                    tool_name,
                    permission_level,
                    serialized_arguments,
                    arguments_hash,
                    idempotency_key,
                    now,
                    now,
                    now,
                ),
            )
        return {
            "invocation": self.get_tool_invocation(invocation_id),
            "created": True,
        }

    def get_tool_invocation(self, invocation_id: str) -> dict:
        return self._get_json_row(
            "tool_invocations",
            invocation_id,
            ("arguments_json", "result_summary_json"),
        )

    def find_tool_invocation(self, *, run_id: str, idempotency_key: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id FROM tool_invocations
            WHERE run_id = ? AND idempotency_key = ?
            """,
            (run_id, idempotency_key),
        ).fetchone()
        return self.get_tool_invocation(str(row["id"])) if row is not None else None

    def complete_tool_invocation(
        self,
        invocation_id: str,
        *,
        result_summary: dict[str, JsonValue],
        mutations: list[MutationInput],
        commit: bool = True,
    ) -> dict:
        now = _now()
        with write_scope(self.connection, commit=commit):
            row = self.connection.execute(
                "SELECT run_id, status, permission_level FROM tool_invocations WHERE id = ?",
                (invocation_id,),
            ).fetchone()
            if row is None:
                raise LookupError("tool invocation not found")
            if row["status"] != "running":
                raise ValueError("only a running tool invocation can complete")
            if row["permission_level"] == 1 and mutations:
                raise PermissionError("level 1 tools cannot mutate state")
            if row["permission_level"] == 2 and any(
                not mutation.get("reversible", False) or "undo" not in mutation
                for mutation in mutations
            ):
                raise PermissionError("level 2 mutations require reversible undo data")
            if row["permission_level"] == 3:
                raise PermissionError(
                    "level 3 tool execution is not enabled in this milestone"
                )
            self.connection.execute(
                """
                UPDATE tool_invocations
                SET status = 'succeeded', result_summary_json = ?, updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    _audit_object(result_summary, label="tool result summary")[0],
                    now,
                    now,
                    invocation_id,
                ),
            )
            for ordinal, mutation in enumerate(mutations):
                if mutation["operation"] not in {"create", "update", "delete"}:
                    raise ValueError("invalid mutation operation")
                if "before" not in mutation and "after" not in mutation:
                    raise ValueError("mutation requires before or after state")
                self.connection.execute(
                    """
                    INSERT INTO state_mutations
                        (id, run_id, tool_invocation_id, ordinal, entity_type,
                         entity_id, operation, before_json, after_json, undo_json,
                         reversible, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mutation["id"],
                        row["run_id"],
                        invocation_id,
                        ordinal,
                        mutation["entity_type"],
                        mutation["entity_id"],
                        mutation["operation"],
                        dump_json(mutation["before"]) if "before" in mutation else None,
                        dump_json(mutation["after"]) if "after" in mutation else None,
                        dump_json(mutation["undo"]) if "undo" in mutation else None,
                        int(mutation.get("reversible", "undo" in mutation)),
                        now,
                    ),
                )
        return self.get_tool_invocation(invocation_id)

    def finish_tool_invocation(
        self,
        invocation_id: str,
        *,
        status: str,
        error_code: str,
        commit: bool = True,
    ) -> dict:
        if status not in {"failed", "cancelled", "denied"}:
            raise ValueError("invalid terminal tool status")
        now = _now()
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """
                UPDATE tool_invocations
                SET status = ?, error_code = ?, error_detail = NULL,
                    updated_at = ?, finished_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (status, error_code, now, now, invocation_id),
            )
            if cursor.rowcount != 1:
                row = self.connection.execute(
                    "SELECT status FROM tool_invocations WHERE id = ?",
                    (invocation_id,),
                ).fetchone()
                if row is None:
                    raise LookupError("tool invocation not found")
                raise ValueError(f"only a running tool invocation can become {status}")
        return self.get_tool_invocation(invocation_id)

    def list_state_mutations(self, invocation_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, run_id, tool_invocation_id, ordinal, entity_type,
                   entity_id, operation, before_json, after_json, undo_json,
                   reversible, created_at, undone_at,
                   undone_by_tool_invocation_id
            FROM state_mutations
            WHERE tool_invocation_id = ? ORDER BY ordinal
            """,
            (invocation_id,),
        ).fetchall()
        return [self._decode_mutation_row(row) for row in rows]

    def get_state_mutation(self, mutation_id: str) -> dict:
        row = self.connection.execute(
            """
            SELECT id, run_id, tool_invocation_id, ordinal, entity_type,
                   entity_id, operation, before_json, after_json, undo_json,
                   reversible, created_at, undone_at,
                   undone_by_tool_invocation_id
            FROM state_mutations WHERE id = ?
            """,
            (mutation_id,),
        ).fetchone()
        if row is None:
            raise LookupError("state mutation not found")
        return self._decode_mutation_row(row)

    def mark_state_mutation_undone(
        self,
        mutation_id: str,
        *,
        undo_invocation_id: str,
        commit: bool = True,
    ) -> dict:
        now = _now()
        with write_scope(self.connection, commit=commit):
            original = self.get_state_mutation(mutation_id)
            self._validate_undo_relationship(
                original, undo_invocation_id=undo_invocation_id
            )
            cursor = self.connection.execute(
                """
                UPDATE state_mutations
                SET undone_at = ?, undone_by_tool_invocation_id = ?
                WHERE id = ? AND reversible = 1 AND undone_at IS NULL
                """,
                (now, undo_invocation_id, mutation_id),
            )
            if cursor.rowcount != 1:
                row = self.connection.execute(
                    "SELECT reversible, undone_at FROM state_mutations WHERE id = ?",
                    (mutation_id,),
                ).fetchone()
                if row is None:
                    raise LookupError("state mutation not found")
                if not row["reversible"]:
                    raise PermissionError("state mutation is not reversible")
                raise ValueError("state mutation has already been undone")
        return self.get_state_mutation(mutation_id)

    def _validate_undo_relationship(
        self, original: dict, *, undo_invocation_id: str
    ) -> None:
        invocation = self.get_tool_invocation(undo_invocation_id)
        if (
            invocation["id"] == original["tool_invocation_id"]
            or invocation["run_id"] != original["run_id"]
            or invocation["permission_level"] != 2
            or invocation["status"] != "succeeded"
            or invocation["tool_name"] != "undo_state_mutation"
            or invocation["arguments"].get("mutation_id") != original["id"]
        ):
            raise PermissionError(
                "undo requires its dedicated succeeded invocation for this mutation"
            )
        inverses = self.list_state_mutations(undo_invocation_id)
        if len(inverses) != 1:
            raise PermissionError("undo invocation must contain exactly one inverse")
        inverse = inverses[0]
        undo = original.get("undo")
        inverse_undo = inverse.get("undo")
        if not isinstance(undo, dict) or not isinstance(inverse_undo, dict):
            raise PermissionError("undo audit is missing typed inverse data")
        if (
            original["entity_type"] != "study_task"
            or original["operation"] != "update"
            or undo.get("operation") != "update"
            or undo.get("entity_type") != original["entity_type"]
            or undo.get("entity_id") != original["entity_id"]
            or inverse["run_id"] != original["run_id"]
            or inverse["entity_type"] != original["entity_type"]
            or inverse["entity_id"] != original["entity_id"]
            or inverse["operation"] != undo.get("operation")
            or inverse["before"] != original["after"]
            or inverse_undo.get("operation") != original["operation"]
            or inverse_undo.get("entity_type") != original["entity_type"]
            or inverse_undo.get("entity_id") != original["entity_id"]
            or inverse_undo.get("restore") != inverse["before"]
        ):
            raise PermissionError(
                "undo invocation does not contain the recorded inverse mutation"
            )
        original_before = original.get("before")
        original_after = original.get("after")
        inverse_after = inverse.get("after")
        if not all(
            isinstance(value, dict)
            for value in (original_before, original_after, inverse_after)
        ):
            raise PermissionError("study task undo requires object snapshots")
        technical = {"revision", "updated_at"}
        expected_business = {
            key: value for key, value in original_before.items() if key not in technical
        }
        inverse_business = {
            key: value for key, value in inverse_after.items() if key not in technical
        }
        original_revision = original_after.get("revision")
        if (
            expected_business != inverse_business
            or not isinstance(original_revision, int)
            or isinstance(original_revision, bool)
            or inverse_after.get("revision") != original_revision + 1
        ):
            raise PermissionError(
                "undo invocation does not contain the recorded inverse mutation"
            )

    def request_approval(
        self,
        *,
        approval_id: str,
        run_id: str,
        invocation_id: str,
        summary: str,
        commit: bool = True,
    ) -> dict:
        now = _now()
        with write_scope(self.connection, commit=commit):
            invocation = self.connection.execute(
                "SELECT permission_level, run_id FROM tool_invocations WHERE id = ?",
                (invocation_id,),
            ).fetchone()
            if invocation is None or invocation["run_id"] != run_id:
                raise LookupError("tool invocation not found for run")
            if invocation["permission_level"] != 3:
                raise ValueError("approval is only valid for permission level 3")
            self.connection.execute(
                """
                INSERT INTO approval_requests
                    (id, run_id, tool_invocation_id, status, summary, requested_at, resolved_at)
                VALUES (?, ?, ?, 'pending', ?, ?, NULL)
                """,
                (approval_id, run_id, invocation_id, summary, now),
            )
        return dict(
            self.connection.execute(
                "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
            ).fetchone()
        )

    def recover_interrupted_runs(self, *, commit: bool = True) -> list[str]:
        now = _now()
        with write_scope(self.connection, commit=commit):
            rows = self.connection.execute(
                "SELECT id FROM agent_runs WHERE status IN ('queued', 'running', 'waiting_approval') ORDER BY id"
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            self.connection.execute(
                """
                UPDATE agent_runs SET status = 'interrupted', updated_at = ?,
                    finished_at = ?, error_code = 'process_restarted',
                    error_detail = 'Agent run was interrupted by restart'
                WHERE status IN ('queued', 'running', 'waiting_approval')
                """,
                (now, now),
            )
            self.connection.execute(
                """
                UPDATE agent_steps SET status = 'interrupted', updated_at = ?,
                    finished_at = ?, error_code = 'process_restarted',
                    error_detail = 'Agent step was interrupted by restart'
                WHERE status IN ('pending', 'running')
                  AND run_id IN (SELECT id FROM agent_runs WHERE status = 'interrupted')
                """,
                (now, now),
            )
            self.connection.execute(
                """
                UPDATE tool_invocations SET status = 'cancelled', updated_at = ?,
                    finished_at = ?, error_code = 'process_restarted',
                    error_detail = 'Tool invocation was interrupted by restart'
                WHERE status IN ('pending', 'running')
                  AND run_id IN (SELECT id FROM agent_runs WHERE status = 'interrupted')
                """,
                (now, now),
            )
            self.connection.execute(
                """
                UPDATE approval_requests SET status = 'cancelled', resolved_at = ?
                WHERE status = 'pending'
                  AND run_id IN (SELECT id FROM agent_runs WHERE status = 'interrupted')
                """,
                (now,),
            )
            for run_id in ids:
                self.append_event(
                    event_id=_recovery_event_id(run_id, "status"),
                    run_id=run_id,
                    event_type="status",
                    payload={"status": "interrupted"},
                    commit=False,
                )
                self.append_event(
                    event_id=_recovery_event_id(run_id, "error"),
                    run_id=run_id,
                    event_type="error",
                    payload={
                        "code": "process_restarted",
                        "message": (
                            "Agent run was interrupted by restart; start a new run "
                            "to continue"
                        ),
                        "retryable": True,
                        "status": "interrupted",
                    },
                    commit=False,
                )
        return ids

    def _get_json_row(
        self, table: str, row_id: str, json_columns: tuple[str, ...]
    ) -> dict:
        if table not in {"agent_steps", "tool_invocations"}:
            raise ValueError("unsupported agent audit table")
        row = self.connection.execute(
            f"SELECT * FROM {table} WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"{table} row not found")
        result = dict(row)
        for column in json_columns:
            value = result.pop(column)
            result[column.removesuffix("_json")] = (
                load_json(value) if value is not None else None
            )
        return result

    @staticmethod
    def _decode_mutation_row(row: sqlite3.Row) -> dict:
        result = dict(row)
        for column in ("before_json", "after_json", "undo_json"):
            value = result.pop(column)
            result[column.removesuffix("_json")] = (
                load_json(value) if value is not None else None
            )
        result["reversible"] = bool(result["reversible"])
        return result
