from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from . import dump_json, load_json, write_scope


_TRANSITIONS = {
    "suspected": {"confirmed", "dismissed"},
    "confirmed": {"improving", "resolved", "dismissed"},
    "improving": {"confirmed", "resolved", "dismissed"},
    "resolved": set(),
    "dismissed": set(),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decode_evidence(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["details"] = load_json(result.pop("details_json"))
    return result


def _decode_misconception(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["creation_payload"] = load_json(result.pop("creation_payload_json"))
    return result


class MisconceptionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_suspected(
        self,
        *,
        misconception_id: str,
        course_id: str,
        concept_id: str,
        label: str,
        description: str,
        confidence: float,
        idempotency_key: str,
        seen_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        creation_payload = {
            "id": misconception_id,
            "course_id": course_id,
            "concept_id": concept_id,
            "label": label,
            "description": description,
            "confidence": confidence,
        }
        existing = self._by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing["creation_payload"] != creation_payload:
                raise ValueError("misconception idempotency key was reused")
            return existing, False
        timestamp = seen_at or _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO misconceptions (
                    id, course_id, concept_id, label, description, status,
                    confidence, confirmation_source, first_seen_at,
                    last_seen_at, resolved_at, idempotency_key,
                    creation_payload_json
                ) VALUES (?, ?, ?, ?, ?, 'suspected', ?, NULL, ?, ?, NULL, ?, ?)
                """,
                (
                    misconception_id,
                    course_id,
                    concept_id,
                    label,
                    description,
                    confidence,
                    timestamp,
                    timestamp,
                    idempotency_key,
                    dump_json(creation_payload),
                ),
            )
        misconception = self.get(misconception_id)
        if misconception is None:  # pragma: no cover
            raise RuntimeError("misconception insert did not persist")
        return misconception, True

    def get(self, misconception_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM misconceptions WHERE id = ?", (misconception_id,)
        ).fetchone()
        return _decode_misconception(row) if row is not None else None

    def list_for_course(
        self, course_id: str, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        status_clause = " AND status = ?" if status else ""
        parameters = (course_id, status) if status else (course_id,)
        rows = self.connection.execute(
            """
            SELECT * FROM misconceptions
            WHERE course_id = ?
            """
            + status_clause
            + " ORDER BY last_seen_at DESC, id",
            parameters,
        ).fetchall()
        return [_decode_misconception(row) for row in rows]

    def list_actionable_for_course(
        self, course_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List unresolved misconceptions with their persisted evidence count."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 200
        ):
            raise ValueError("limit must be between 1 and 200")
        rows = self.connection.execute(
            """
            SELECT m.*, COUNT(e.id) AS evidence_count
            FROM misconceptions AS m
            LEFT JOIN misconception_evidence AS e ON e.misconception_id = m.id
            WHERE m.course_id = ?
              AND m.status IN ('suspected', 'confirmed', 'improving')
            GROUP BY m.id
            ORDER BY evidence_count DESC, m.last_seen_at DESC, m.id
            LIMIT ?
            """,
            (course_id, limit),
        ).fetchall()
        return [_decode_misconception(row) for row in rows]

    def add_evidence(
        self,
        *,
        evidence_id: str,
        misconception_id: str,
        evidence_type: str,
        confidence: float,
        details: dict[str, Any],
        idempotency_key: str,
        mastery_evidence_id: str | None = None,
        attempt_id: str | None = None,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        existing = self._evidence_by_idempotency_key(idempotency_key)
        if existing is not None:
            expected = {
                "id": evidence_id,
                "misconception_id": misconception_id,
                "mastery_evidence_id": mastery_evidence_id,
                "attempt_id": attempt_id,
                "evidence_type": evidence_type,
                "confidence": confidence,
                "details": details,
            }
            if any(existing[key] != value for key, value in expected.items()):
                raise ValueError("misconception evidence idempotency key was reused")
            return existing, False
        timestamp = created_at or _now()
        details_json = dump_json(details)
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO misconception_evidence (
                    id, misconception_id, mastery_evidence_id, attempt_id,
                    evidence_type, confidence, details_json, idempotency_key,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    misconception_id,
                    mastery_evidence_id,
                    attempt_id,
                    evidence_type,
                    confidence,
                    details_json,
                    idempotency_key,
                    timestamp,
                ),
            )
            updated = self.connection.execute(
                """
                UPDATE misconceptions
                SET confidence = MAX(confidence, ?), last_seen_at = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (confidence, timestamp, misconception_id),
            )
            if updated.rowcount != 1:
                raise LookupError("misconception not found")
        evidence = self.get_evidence(evidence_id)
        if evidence is None:  # pragma: no cover
            raise RuntimeError("misconception evidence insert did not persist")
        return evidence, True

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM misconception_evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        return _decode_evidence(row) if row is not None else None

    def transition(
        self,
        misconception_id: str,
        *,
        to_status: str,
        expected_revision: int,
        confirmation_source: str | None = None,
        changed_at: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        timestamp = changed_at or _now()
        with write_scope(self.connection, commit=commit):
            current = self.get(misconception_id)
            if current is None:
                raise LookupError("misconception not found")
            if to_status not in _TRANSITIONS[str(current["status"])]:
                raise ValueError(
                    "invalid misconception transition: "
                    f"{current['status']} -> {to_status}"
                )
            if to_status == "confirmed" and confirmation_source not in {
                "deterministic_rule",
                "user",
            }:
                raise ValueError("confirmed misconceptions require a trusted source")

            resolved_at = timestamp if to_status == "resolved" else None
            source = confirmation_source or current["confirmation_source"]
            cursor = self.connection.execute(
                """
                UPDATE misconceptions
                SET status = ?, confirmation_source = ?, resolved_at = ?,
                    last_seen_at = ?, revision = revision + 1
                WHERE id = ? AND revision = ?
                """,
                (
                    to_status,
                    source,
                    resolved_at,
                    timestamp,
                    misconception_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("misconception was updated concurrently")
        result = self.get(misconception_id)
        if result is None:  # pragma: no cover
            raise RuntimeError("misconception disappeared after update")
        return result

    def _by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM misconceptions WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _decode_misconception(row) if row is not None else None

    def _evidence_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM misconception_evidence WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _decode_evidence(row) if row is not None else None
