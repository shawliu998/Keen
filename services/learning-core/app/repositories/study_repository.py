from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from . import JsonValue, dump_json, load_json, write_scope


class StudyUnitInput(TypedDict):
    id: str
    title: str
    objective: str
    estimated_minutes: int
    concept_ids: list[str]
    source_chunk_ids: list[str]
    content: NotRequired[str]
    status: NotRequired[str]
    concept_id: NotRequired[str | None]


_SESSION_TRANSITIONS = {
    "draft": frozenset({"goal_confirmation", "paused", "cancelled", "failed"}),
    "goal_confirmation": frozenset({"diagnosing", "paused", "cancelled", "failed"}),
    "diagnosing": frozenset({"planning", "paused", "cancelled", "failed"}),
    "planning": frozenset({"studying", "paused", "cancelled", "failed"}),
    "studying": frozenset(
        {
            "checkpoint",
            "active_recall",
            "practicing",
            "summarizing",
            "paused",
            "cancelled",
            "failed",
        }
    ),
    "checkpoint": frozenset(
        {"studying", "active_recall", "practicing", "paused", "cancelled", "failed"}
    ),
    "active_recall": frozenset(
        {"studying", "practicing", "summarizing", "paused", "cancelled", "failed"}
    ),
    "practicing": frozenset(
        {"studying", "checkpoint", "summarizing", "paused", "cancelled", "failed"}
    ),
    "summarizing": frozenset({"review_scheduling", "paused", "cancelled", "failed"}),
    "review_scheduling": frozenset({"completed", "paused", "cancelled", "failed"}),
    "paused": frozenset(),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "failed": frozenset(),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _string_array(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return value


class StudyRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_session(
        self,
        *,
        session_id: str,
        course_id: str,
        title: str,
        mode: str,
        goal: str,
        estimated_minutes: int,
        goal_scope: dict[str, JsonValue] | None = None,
        preferences: dict[str, JsonValue] | None = None,
        difficulty: dict[str, JsonValue] | None = None,
        conversation_id: str | None = None,
        originating_task_id: str | None = None,
        created_at: str | None = None,
        commit: bool = True,
    ) -> dict:
        if mode not in {"teach", "study", "review", "plan"}:
            raise ValueError("invalid study mode")
        for label, value in (
            ("goal scope", goal_scope),
            ("preferences", preferences),
            ("difficulty", difficulty),
        ):
            if value is not None and not isinstance(value, dict):
                raise ValueError(f"{label} must be an object")
        now = created_at or _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO study_sessions
                    (id, course_id, conversation_id, originating_task_id, title, mode, goal,
                     goal_scope_json, preferences_json, difficulty_json, status,
                     resume_from_status, revision, progress, estimated_minutes,
                     created_at, updated_at, started_at, finished_at, current_unit_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', NULL, 0, 0, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    session_id,
                    course_id,
                    conversation_id,
                    originating_task_id,
                    title,
                    mode,
                    goal,
                    dump_json(goal_scope or {}),
                    dump_json(preferences or {}),
                    dump_json(difficulty or {}),
                    estimated_minutes,
                    now,
                    now,
                ),
            )
            self._append_event(session_id, "created", {"status": "draft"}, now)
        return self._require_session(session_id)

    def get_session(self, session_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM study_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        for column in ("goal_scope_json", "preferences_json", "difficulty_json"):
            result[column.removesuffix("_json")] = load_json(result.pop(column))
        return result

    def list_incomplete_for_course(
        self, course_id: str, *, limit: int = 50
    ) -> list[dict]:
        """List resumable sessions for one course in a stable order.

        This is deliberately read-only.  ``draft`` sessions are included because
        they are recoverable learning work, while terminal sessions are excluded.
        """

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 200
        ):
            raise ValueError("limit must be between 1 and 200")
        rows = self.connection.execute(
            """
            SELECT * FROM study_sessions
            WHERE course_id = ?
              AND status NOT IN ('completed', 'cancelled', 'failed')
            ORDER BY
                CASE WHEN status = 'paused' THEN 0 ELSE 1 END,
                updated_at,
                id
            LIMIT ?
            """,
            (course_id, limit),
        ).fetchall()
        result: list[dict] = []
        for row in rows:
            session = dict(row)
            for column in ("goal_scope_json", "preferences_json", "difficulty_json"):
                session[column.removesuffix("_json")] = load_json(session.pop(column))
            result.append(session)
        return result

    def transition_session(
        self,
        session_id: str,
        *,
        status: str,
        expected_revision: int,
        progress: float | None = None,
        current_unit_id: str | None = None,
        updated_at: str | None = None,
        commit: bool = True,
    ) -> dict:
        current = self._require_session(session_id)
        from_status = str(current["status"])
        if int(current["revision"]) != expected_revision:
            raise RuntimeError("study session revision conflict")
        resume_from: str | None = None
        if from_status == "paused":
            expected = current["resume_from_status"]
            if status != expected:
                raise ValueError(f"paused session must resume to {expected}")
        elif status == "paused":
            if from_status in {"completed", "cancelled", "failed"}:
                raise ValueError("terminal session cannot be paused")
            resume_from = from_status
        elif status not in _SESSION_TRANSITIONS.get(from_status, frozenset()):
            raise ValueError(
                f"invalid study session transition: {from_status} -> {status}"
            )
        if progress is not None and not 0 <= progress <= 1:
            raise ValueError("progress must be between 0 and 1")
        now = updated_at or _now()
        terminal = status in {"completed", "cancelled", "failed"}
        with write_scope(self.connection, commit=commit):
            if current_unit_id is not None:
                owned = self.connection.execute(
                    """
                    SELECT 1 FROM study_units u JOIN study_plan_versions p ON p.id = u.plan_version_id
                    WHERE u.id = ? AND p.session_id = ?
                    """,
                    (current_unit_id, session_id),
                ).fetchone()
                if owned is None:
                    raise LookupError("study unit does not belong to session")
            cursor = self.connection.execute(
                """
                UPDATE study_sessions
                SET status = ?, resume_from_status = ?, revision = revision + 1,
                    progress = COALESCE(?, progress),
                    current_unit_id = COALESCE(?, current_unit_id), updated_at = ?,
                    started_at = CASE WHEN ? != 'draft' AND started_at IS NULL THEN ? ELSE started_at END,
                    finished_at = CASE WHEN ? THEN ? ELSE NULL END
                WHERE id = ? AND revision = ?
                """,
                (
                    status,
                    resume_from,
                    progress,
                    current_unit_id,
                    now,
                    status,
                    now,
                    terminal,
                    now,
                    session_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("study session revision conflict")
            self._append_event(
                session_id, "status_changed", {"from": from_status, "to": status}, now
            )
        return self._require_session(session_id)

    def save_plan(
        self,
        *,
        plan_id: str,
        session_id: str,
        version: int,
        rationale: str,
        units: list[StudyUnitInput],
        created_at: str | None = None,
        commit: bool = True,
    ) -> dict:
        if version < 1 or not 2 <= len(units) <= 8:
            raise ValueError("a plan needs a positive version and 2 to 8 units")
        now = created_at or _now()
        with write_scope(self.connection, commit=commit):
            session = self.connection.execute(
                "SELECT course_id FROM study_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise LookupError("study session not found")
            for unit in units:
                concept_ids = _string_array(unit["concept_ids"], label="concept ids")
                source_ids = _string_array(
                    unit["source_chunk_ids"], label="source chunk ids"
                )
                if not concept_ids or not source_ids:
                    raise ValueError(
                        "each study unit requires concepts and source chunks"
                    )
                self._validate_scoped_ids(
                    course_id=session["course_id"],
                    concept_ids=concept_ids,
                    source_chunk_ids=source_ids,
                )
            existing = self.connection.execute(
                "SELECT id, rationale FROM study_plan_versions WHERE session_id = ? AND version = ?",
                (session_id, version),
            ).fetchone()
            if existing is not None:
                actual = self.list_plan_units(existing["id"])
                expected = [
                    self._normalized_unit(unit, ordinal)
                    for ordinal, unit in enumerate(units)
                ]
                comparable = (
                    [{key: item[key] for key in expected[0].keys()} for item in actual]
                    if expected
                    else []
                )
                if (
                    existing["id"] != plan_id
                    or existing["rationale"] != rationale
                    or comparable != expected
                ):
                    raise ValueError(
                        "plan version was replayed with a different payload"
                    )
                return {
                    "id": plan_id,
                    "session_id": session_id,
                    "version": version,
                    "rationale": rationale,
                    "units": actual,
                }
            self.connection.execute(
                "INSERT INTO study_plan_versions (id, session_id, version, rationale, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan_id, session_id, version, rationale, now),
            )
            for ordinal, unit in enumerate(units):
                normalized = self._normalized_unit(unit, ordinal)
                self.connection.execute(
                    """
                    INSERT INTO study_units
                        (id, plan_version_id, ordinal, concept_id, concept_ids_json,
                         source_chunk_ids_json, title, objective, content,
                         estimated_minutes, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        unit["id"],
                        plan_id,
                        ordinal,
                        unit.get("concept_id"),
                        dump_json(normalized["concept_ids"]),
                        dump_json(normalized["source_chunk_ids"]),
                        unit["title"],
                        unit["objective"],
                        unit.get("content", ""),
                        unit["estimated_minutes"],
                        unit.get("status", "locked"),
                        now,
                        now,
                    ),
                )
            self._append_event(
                session_id,
                "plan_created",
                {"plan_id": plan_id, "version": version},
                now,
            )
        return {
            "id": plan_id,
            "session_id": session_id,
            "version": version,
            "rationale": rationale,
            "units": self.list_plan_units(plan_id),
        }

    def list_plan_units(self, plan_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM study_units WHERE plan_version_id = ? ORDER BY ordinal",
            (plan_id,),
        ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["concept_ids"] = load_json(item.pop("concept_ids_json"))
            item["source_chunk_ids"] = load_json(item.pop("source_chunk_ids_json"))
            result.append(item)
        return result

    def get_current_or_latest_plan(self, session_id: str) -> dict | None:
        """Return the plan containing the current unit, otherwise the latest plan.

        Selection and unit loading are read-only.  Relationship validation is
        intentionally left to the course-scoped service boundary.
        """

        session = self.connection.execute(
            "SELECT current_unit_id FROM study_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            return None
        current_unit_id = session["current_unit_id"]
        if current_unit_id is not None:
            row = self.connection.execute(
                """
                SELECT p.id, p.session_id, p.version, p.rationale
                FROM study_plan_versions p
                JOIN study_units u ON u.plan_version_id = p.id
                WHERE u.id = ? AND p.session_id = ?
                """,
                (current_unit_id, session_id),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT id, session_id, version, rationale
                FROM study_plan_versions
                WHERE session_id = ?
                ORDER BY version DESC, id
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["units"] = self.list_plan_units(str(result["id"]))
        return result

    def create_checkpoint(
        self,
        *,
        checkpoint_id: str,
        session_id: str,
        kind: str,
        prompt: str,
        unit_id: str | None = None,
        commit: bool = True,
    ) -> dict:
        if kind not in {
            "diagnostic",
            "comprehension",
            "active_recall",
            "practice",
            "reflection",
        }:
            raise ValueError("invalid checkpoint kind")
        now = _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO study_checkpoints
                    (id, session_id, unit_id, kind, prompt, response, status, created_at, answered_at)
                VALUES (?, ?, ?, ?, ?, NULL, 'pending', ?, NULL)
                """,
                (checkpoint_id, session_id, unit_id, kind, prompt, now),
            )
            self._append_event(
                session_id, "checkpoint_created", {"checkpoint_id": checkpoint_id}, now
            )
        return dict(
            self.connection.execute(
                "SELECT * FROM study_checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
        )

    def create_diagnostic_checkpoint(
        self,
        *,
        checkpoint_id: str,
        session_id: str,
        unit_id: str,
        prompt: str,
        idempotency_key: str,
        payload_fingerprint: str,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict, bool]:
        """Create one diagnostic checkpoint, replaying only the same request."""

        existing = self.connection.execute(
            "SELECT * FROM study_checkpoints WHERE diagnostic_begin_idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            item = dict(existing)
            if (
                item["session_id"] != session_id
                or item["unit_id"] != unit_id
                or item["kind"] != "diagnostic"
                or item["diagnostic_begin_payload_fingerprint"] != payload_fingerprint
            ):
                raise ValueError("diagnostic begin idempotency key was reused")
            return item, False
        now = created_at or _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO study_checkpoints
                    (id, session_id, unit_id, kind, prompt, response, status, created_at,
                     answered_at, diagnostic_begin_idempotency_key,
                     diagnostic_begin_payload_fingerprint)
                VALUES (?, ?, ?, 'diagnostic', ?, NULL, 'pending', ?, NULL, ?, ?)
                """,
                (
                    checkpoint_id,
                    session_id,
                    unit_id,
                    prompt,
                    now,
                    idempotency_key,
                    payload_fingerprint,
                ),
            )
            self._append_event(
                session_id, "checkpoint_created", {"checkpoint_id": checkpoint_id}, now
            )
        row = self.connection.execute(
            "SELECT * FROM study_checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        if row is None:  # pragma: no cover - guarded by insert
            raise RuntimeError("diagnostic checkpoint insert did not persist")
        return dict(row), True

    def get_checkpoint(self, checkpoint_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM study_checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def answer_diagnostic_checkpoint(
        self,
        *,
        checkpoint_id: str,
        response: str,
        idempotency_key: str,
        payload_fingerprint: str,
        mastery_evidence_id: str,
        answered_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict, bool]:
        """Persist one unscored diagnostic reflection with durable replay semantics."""

        existing = self.get_checkpoint(checkpoint_id)
        if existing is None:
            raise LookupError("study checkpoint not found")
        if existing["diagnostic_answer_idempotency_key"] is not None:
            if (
                existing["diagnostic_answer_idempotency_key"] != idempotency_key
                or existing["diagnostic_answer_payload_fingerprint"]
                != payload_fingerprint
            ):
                raise ValueError("diagnostic answer is already recorded")
            return existing, False
        if existing["kind"] != "diagnostic" or existing["status"] != "pending":
            raise ValueError("diagnostic checkpoint is not pending")
        now = answered_at or _now()
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """
                UPDATE study_checkpoints
                SET response = ?, status = 'answered', answered_at = ?,
                    diagnostic_answer_idempotency_key = ?,
                    diagnostic_answer_payload_fingerprint = ?, mastery_evidence_id = ?
                WHERE id = ? AND status = 'pending'
                  AND diagnostic_answer_idempotency_key IS NULL
                """,
                (
                    response,
                    now,
                    idempotency_key,
                    payload_fingerprint,
                    mastery_evidence_id,
                    checkpoint_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("diagnostic checkpoint revision conflict")
            self._append_event(
                existing["session_id"],
                "checkpoint_answered",
                {"checkpoint_id": checkpoint_id, "kind": "diagnostic"},
                now,
            )
        updated = self.get_checkpoint(checkpoint_id)
        if updated is None:  # pragma: no cover
            raise RuntimeError("diagnostic checkpoint disappeared")
        return updated, True

    def activate_first_unit(
        self,
        *,
        unit_id: str,
        session_id: str,
        updated_at: str | None = None,
        commit: bool = True,
    ) -> dict:
        """Move only a ready unit belonging to a session into the active state."""

        now = updated_at or _now()
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """
                UPDATE study_units
                SET status = 'active', updated_at = ?
                WHERE id = ? AND status = 'ready' AND EXISTS (
                    SELECT 1 FROM study_plan_versions p
                    WHERE p.id = study_units.plan_version_id AND p.session_id = ?
                )
                """,
                (now, unit_id, session_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("study unit is not ready for activation")
            self._append_event(
                session_id,
                "unit_changed",
                {"unit_id": unit_id, "from": "ready", "to": "active"},
                now,
            )
        row = self.connection.execute(
            "SELECT * FROM study_units WHERE id = ?", (unit_id,)
        ).fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError("study unit disappeared")
        result = dict(row)
        result["concept_ids"] = load_json(result.pop("concept_ids_json"))
        result["source_chunk_ids"] = load_json(result.pop("source_chunk_ids_json"))
        return result

    def clear_current_unit(
        self,
        *,
        session_id: str,
        expected_revision: int,
        updated_at: str | None = None,
        commit: bool = True,
    ) -> dict:
        """CAS-clear the active-unit pointer inside a caller-owned unit swap.

        This deliberately cannot commit independently: a persisted null pointer
        while the old unit remains active would be a durable half-transition.
        The enclosing operation owns the only revision/event for the complete
        swap and must commit or roll back all unit and pointer writes together.
        """

        if commit:
            raise ValueError("clear_current_unit requires commit=False")
        now = updated_at or _now()
        with write_scope(self.connection, commit=commit):
            active = self.connection.execute(
                """
                SELECT s.current_unit_id, u.status
                FROM study_sessions s
                LEFT JOIN study_units u ON u.id = s.current_unit_id
                WHERE s.id = ? AND s.revision = ?
                """,
                (session_id, expected_revision),
            ).fetchone()
            if (
                active is None
                or active["current_unit_id"] is None
                or active["status"] != "active"
            ):
                raise RuntimeError("study session revision conflict")
            cursor = self.connection.execute(
                """
                UPDATE study_sessions
                SET current_unit_id = NULL, updated_at = ?
                WHERE id = ? AND revision = ? AND current_unit_id IS NOT NULL
                """,
                (now, session_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("study session revision conflict")
            # This is only the pointer half of a caller-controlled unit swap.
            # Emitting ``unit_changed`` here would falsely claim that the unit
            # itself stopped being active before its status is actually changed.
        return self._require_session(session_id)

    def recover_active_sessions(self, *, commit: bool = True) -> list[str]:
        now = _now()
        active = tuple(
            status
            for status in _SESSION_TRANSITIONS
            if status not in {"draft", "paused", "completed", "cancelled", "failed"}
        )
        placeholders = ",".join("?" for _ in active)
        with write_scope(self.connection, commit=commit):
            rows = self.connection.execute(
                f"SELECT id, status FROM study_sessions WHERE status IN ({placeholders}) ORDER BY id",
                active,
            ).fetchall()
            for row in rows:
                self.connection.execute(
                    """
                    UPDATE study_sessions SET status = 'paused', resume_from_status = ?,
                        revision = revision + 1, updated_at = ? WHERE id = ?
                    """,
                    (row["status"], now, row["id"]),
                )
                self._append_event(
                    row["id"], "recovered", {"resume_from": row["status"]}, now
                )
        return [str(row["id"]) for row in rows]

    def _append_event(
        self, session_id: str, event_type: str, payload: JsonValue, created_at: str
    ) -> None:
        sequence = int(
            self.connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM study_session_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        )
        self.connection.execute(
            "INSERT INTO study_session_events (id, session_id, sequence, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"{session_id}:event:{sequence}",
                session_id,
                sequence,
                event_type,
                dump_json(payload),
                created_at,
            ),
        )

    def _require_session(self, session_id: str) -> dict:
        result = self.get_session(session_id)
        if result is None:
            raise LookupError("study session not found")
        return result

    @staticmethod
    def _normalized_unit(unit: StudyUnitInput, ordinal: int) -> dict:
        status = unit.get("status", "locked")
        if status not in {"locked", "ready", "active", "completed", "skipped"}:
            raise ValueError("invalid study unit status")
        return {
            "id": unit["id"],
            "ordinal": ordinal,
            "concept_id": unit.get("concept_id"),
            "concept_ids": _string_array(unit["concept_ids"], label="concept ids"),
            "source_chunk_ids": _string_array(
                unit["source_chunk_ids"], label="source chunk ids"
            ),
            "title": unit["title"],
            "objective": unit["objective"],
            "content": unit.get("content", ""),
            "estimated_minutes": unit["estimated_minutes"],
            "status": status,
        }

    def _validate_scoped_ids(
        self, *, course_id: str, concept_ids: list[str], source_chunk_ids: list[str]
    ) -> None:
        concept_count = int(
            self.connection.execute(
                f"SELECT COUNT(*) FROM concepts WHERE course_id = ? AND id IN ({','.join('?' for _ in concept_ids)})",
                (course_id, *concept_ids),
            ).fetchone()[0]
        )
        if concept_count != len(set(concept_ids)):
            raise LookupError("study unit concept is missing or outside the course")
        source_count = int(
            self.connection.execute(
                f"""
            SELECT COUNT(DISTINCT ch.id)
            FROM document_chunks ch
            JOIN course_documents cd ON cd.document_id = ch.document_id
            WHERE cd.course_id = ? AND ch.id IN ({",".join("?" for _ in source_chunk_ids)})
            """,
                (course_id, *source_chunk_ids),
            ).fetchone()[0]
        )
        if source_count != len(set(source_chunk_ids)):
            raise LookupError(
                "study unit source chunk is missing or outside the course"
            )
