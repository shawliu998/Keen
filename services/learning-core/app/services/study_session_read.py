"""Read one persisted study session without trusting stored relationships."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from app.repositories.study_repository import StudyRepository


StudySessionReadOutcome = Literal["ready", "plan_unavailable"]


@dataclass(frozen=True, slots=True)
class StudySessionReadResult:
    outcome: StudySessionReadOutcome
    course_id: str
    session: dict[str, Any]
    plan: dict[str, Any] | None
    current_unit_id: str | None


class StudySessionReadService:
    """Return the current plan needed to recover a local study session.

    The lookup is scoped by both identifiers before any row is decoded.  A
    missing or foreign session therefore has the same result, while malformed
    relationships in a visible session fail closed at the API boundary.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, *, course_id: str, session_id: str) -> StudySessionReadResult | None:
        scoped_course_id = _identifier(course_id, label="course_id")
        scoped_session_id = _identifier(session_id, label="session_id")
        with _read_scope(self.connection):
            return self._get(course_id=scoped_course_id, session_id=scoped_session_id)

    def _get(self, *, course_id: str, session_id: str) -> StudySessionReadResult | None:
        row = self.connection.execute(
            """
            SELECT id, course_id, originating_task_id, title, mode, goal,
                   estimated_minutes, status, progress, revision, current_unit_id,
                   created_at, updated_at, started_at
            FROM study_sessions
            WHERE id = ? AND course_id = ?
            """,
            (session_id, course_id),
        ).fetchone()
        if row is None:
            return None
        session = dict(row)
        self._validate_originating_task(session, course_id=course_id)

        plan = StudyRepository(self.connection).get_current_or_latest_plan(session_id)
        if plan is None:
            if session["current_unit_id"] is not None:
                raise RuntimeError("study session current unit has no plan")
            return StudySessionReadResult(
                outcome="plan_unavailable",
                course_id=course_id,
                session=session,
                plan=None,
                current_unit_id=None,
            )

        if plan.get("session_id") != session_id:
            raise RuntimeError("selected study plan is outside the session")
        units = self._units(
            plan_id=str(plan["id"]),
            course_id=course_id,
            stored_units=plan.pop("units"),
        )
        plan["units"] = units
        current_unit_id = session["current_unit_id"]
        if current_unit_id is not None and not any(
            unit["id"] == current_unit_id for unit in units
        ):
            raise RuntimeError("study session current unit is outside selected plan")
        return StudySessionReadResult(
            outcome="ready",
            course_id=course_id,
            session=session,
            plan=plan,
            current_unit_id=current_unit_id,
        )

    def _validate_originating_task(
        self, session: dict[str, Any], *, course_id: str
    ) -> None:
        task_id = session["originating_task_id"]
        if task_id is None:
            return
        task = self.connection.execute(
            "SELECT id, course_id FROM study_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if task is None or task["course_id"] != course_id:
            raise RuntimeError("study session originating task is inconsistent")

    def _units(
        self, *, plan_id: str, course_id: str, stored_units: object
    ) -> list[dict[str, Any]]:
        if not isinstance(stored_units, list):
            raise ValueError("selected study plan units are invalid")
        if not 2 <= len(stored_units) <= 8:
            raise RuntimeError("selected study plan has an invalid unit count")
        if [int(unit["ordinal"]) for unit in stored_units] != list(
            range(len(stored_units))
        ):
            raise RuntimeError("selected study plan has invalid unit ordering")
        units: list[dict[str, Any]] = []
        for stored_unit in stored_units:
            if not isinstance(stored_unit, dict):
                raise ValueError("selected study unit is invalid")
            unit = dict(stored_unit)
            if unit["plan_version_id"] != plan_id:
                raise RuntimeError("study unit is outside selected plan")
            concept_ids = _stored_identifiers(
                unit.pop("concept_ids"), label="concept_ids"
            )
            source_chunk_ids = _stored_identifiers(
                unit.pop("source_chunk_ids"),
                label="source_chunk_ids",
            )
            if not concept_ids or not source_chunk_ids:
                raise ValueError("study unit source relationships are empty")
            concept_id = unit["concept_id"]
            if concept_id is not None and concept_id not in concept_ids:
                raise RuntimeError("study unit primary concept is inconsistent")
            self._validate_concepts(course_id=course_id, concept_ids=concept_ids)
            self._validate_source_chunks(
                course_id=course_id, source_chunk_ids=source_chunk_ids
            )
            unit["concept_ids"] = concept_ids
            unit["source_chunk_ids"] = source_chunk_ids
            units.append(unit)
        return units

    def _validate_concepts(self, *, course_id: str, concept_ids: list[str]) -> None:
        placeholders = ",".join("?" for _ in concept_ids)
        rows = self.connection.execute(
            f"SELECT id FROM concepts WHERE course_id = ? AND id IN ({placeholders})",
            (course_id, *concept_ids),
        ).fetchall()
        if {str(row["id"]) for row in rows} != set(concept_ids):
            raise RuntimeError("study unit concept is outside the session course")

    def _validate_source_chunks(
        self, *, course_id: str, source_chunk_ids: list[str]
    ) -> None:
        placeholders = ",".join("?" for _ in source_chunk_ids)
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT ch.id
            FROM document_chunks ch
            JOIN course_documents cd ON cd.document_id = ch.document_id
            WHERE cd.course_id = ? AND ch.id IN ({placeholders})
            """,
            (course_id, *source_chunk_ids),
        ).fetchall()
        if {str(row["id"]) for row in rows} != set(source_chunk_ids):
            raise RuntimeError("study unit source is outside the session course")


def _identifier(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a non-empty identifier")
    return value


@contextmanager
def _read_scope(connection: sqlite3.Connection) -> Iterator[None]:
    """Keep all relationship checks on one SQLite snapshot."""

    owns_transaction = not connection.in_transaction
    if owns_transaction:
        connection.execute("BEGIN")
    try:
        yield
    finally:
        if owns_transaction and connection.in_transaction:
            connection.rollback()


def _stored_identifiers(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError(f"stored {label} are invalid")
    if any(not isinstance(item, str) or not item or len(item) > 128 for item in value):
        raise ValueError(f"stored {label} are invalid")
    if len(set(value)) != len(value):
        raise ValueError(f"stored {label} contain duplicates")
    return value


__all__ = ["StudySessionReadResult", "StudySessionReadService"]
