from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime
from typing import Any

from . import dump_json, load_json, write_scope


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return dump_json(value)


def _decode_task(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["priority_components"] = load_json(result.pop("priority_components_json"))
    creation_payload_json = result.pop("creation_payload_json")
    result["creation_payload"] = (
        load_json(creation_payload_json) if creation_payload_json is not None else None
    )
    return result


def _decode_feedback(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["details"] = load_json(result.pop("details_json"))
    return result


class TaskRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_task(
        self,
        *,
        task_id: str,
        course_id: str,
        title: str,
        reason: str,
        due_at: str,
        estimated_minutes: int,
        source_type: str,
        source_id: str | None,
        priority_score: float,
        priority_components: dict[str, Any],
        recommended_reason: str,
        idempotency_key: str,
        concept_id: str | None = None,
        scheduled_for: str | None = None,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        if (
            isinstance(priority_score, bool)
            or not isinstance(priority_score, (int, float))
            or not math.isfinite(priority_score)
            or priority_score < 0
        ):
            raise ValueError("task priority score must be finite and non-negative")
        priority_score = float(priority_score)
        creation_payload = {
            "id": task_id,
            "course_id": course_id,
            "concept_id": concept_id,
            "title": title,
            "reason": reason,
            "due_at": due_at,
            "estimated_minutes": estimated_minutes,
            "source_type": source_type,
            "source_id": source_id,
            "priority_score": priority_score,
            "priority_components": priority_components,
            "recommended_reason": recommended_reason,
            "scheduled_for": scheduled_for,
        }
        timestamp = created_at or _now()
        with write_scope(self.connection, commit=commit):
            # The idempotency lookup must share the write transaction with the
            # insert.  Looking it up before BEGIN IMMEDIATE lets two sidecars
            # both observe absence and makes the second hit a UNIQUE error.
            existing = self._by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing["creation_payload"] != creation_payload:
                    raise ValueError("study task idempotency key was reused")
                return existing, False
            if concept_id is not None:
                concept = self.connection.execute(
                    "SELECT 1 FROM concepts WHERE id = ? AND course_id = ?",
                    (concept_id, course_id),
                ).fetchone()
                if concept is None:
                    raise LookupError("concept not found in course")
            self._validate_source(
                course_id=course_id,
                concept_id=concept_id,
                source_type=source_type,
                source_id=source_id,
            )
            self.connection.execute(
                """
                INSERT INTO study_tasks (
                    id, course_id, concept_id, title, reason, due_at,
                    estimated_minutes, status, created_at, updated_at,
                    source_type, source_id, priority_score,
                    priority_components_json, recommended_reason, scheduled_for,
                    completed_at, snoozed_until, idempotency_key,
                    creation_payload_json, revision
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, 'upcoming', ?, ?, ?, ?, ?, ?, ?, ?,
                    NULL, NULL, ?, ?, 0
                )
                """,
                (
                    task_id,
                    course_id,
                    concept_id,
                    title,
                    reason,
                    due_at,
                    estimated_minutes,
                    timestamp,
                    timestamp,
                    source_type,
                    source_id,
                    priority_score,
                    _json(priority_components),
                    recommended_reason,
                    scheduled_for,
                    idempotency_key,
                    _json(creation_payload),
                ),
            )
        task = self.get(task_id)
        if task is None:  # pragma: no cover
            raise RuntimeError("study task insert did not persist")
        return task, True

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return _decode_task(row) if row is not None else None

    def find_active_recommendation(
        self,
        *,
        course_id: str,
        source_type: str,
        source_id: str,
        concept_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return an active task that already covers the real target.

        A source-backed target (review or study session) matches its stable
        source pair.  A concept-backed target additionally matches older and
        manual tasks through their real ``concept_id``.  This intentionally
        avoids treating a missing coordinator payload as permission to create
        a second active action for the learner.
        """

        row = self.connection.execute(
            """
            SELECT * FROM study_tasks
            WHERE course_id = ?
              AND status IN ('upcoming', 'overdue')
              AND (
                    (source_type = ? AND source_id = ?)
                    OR (? IS NOT NULL AND concept_id = ?)
                  )
            ORDER BY created_at, id
            LIMIT 1
            """,
            (course_id, source_type, source_id, concept_id, concept_id),
        ).fetchone()
        return _decode_task(row) if row is not None else None

    def find_completed_recommendation_for_day(
        self,
        *,
        course_id: str,
        source_type: str,
        source_id: str,
        concept_id: str | None,
        candidate_id: str,
        completed_from: str,
        completed_through: str,
    ) -> dict[str, Any] | None:
        """Return one exact generated recommendation completed in a UTC range."""

        row = self.connection.execute(
            """
            SELECT * FROM study_tasks
            WHERE course_id = ?
              AND status = 'completed'
              AND completed_at IS NOT NULL
              AND completed_at >= ?
              AND completed_at <= ?
              AND source_type = ?
              AND source_id = ?
              AND concept_id IS ?
              AND json_extract(
                    priority_components_json,
                    '$.recommendation_algorithm_version'
                  ) = 'autonomous-recommendation/1.0.0'
              AND json_extract(priority_components_json, '$.candidate_id') = ?
            ORDER BY completed_at DESC, id DESC
            LIMIT 1
            """,
            (
                course_id,
                completed_from,
                completed_through,
                source_type,
                source_id,
                concept_id,
                candidate_id,
            ),
        ).fetchone()
        return _decode_task(row) if row is not None else None

    def list_feed(
        self,
        *,
        as_of: str,
        course_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("feed limit must be between 1 and 200")
        course_clause = " AND course_id = ?" if course_id else ""
        parameters: list[Any] = [as_of, as_of]
        if course_id:
            parameters.append(course_id)
        parameters.append(limit)
        rows = self.connection.execute(
            """
            SELECT * FROM study_tasks
            WHERE status IN ('upcoming', 'overdue')
              AND (scheduled_for IS NULL OR scheduled_for <= ?)
              AND (snoozed_until IS NULL OR snoozed_until <= ?)
            """
            + course_clause
            + """
            ORDER BY priority_score DESC, due_at, id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [_decode_task(row) for row in rows]

    def list_completed_for_course(
        self,
        *,
        course_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the most recently completed tasks for one exact course."""

        if not isinstance(course_id, str) or not course_id.strip():
            raise ValueError("course_id must be a non-empty string")
        if limit < 1 or limit > 50:
            raise ValueError("completed task limit must be between 1 and 50")
        rows = self.connection.execute(
            """
            SELECT * FROM study_tasks
            WHERE course_id = ?
              AND status = 'completed'
              AND completed_at IS NOT NULL
            ORDER BY completed_at DESC, id DESC
            LIMIT ?
            """,
            (course_id.strip(), limit),
        ).fetchall()
        return [_decode_task(row) for row in rows]

    def complete_active_review_task(
        self,
        *,
        task_id: str,
        course_id: str,
        review_item_id: str,
        expected_revision: int,
        completed_at: str,
        commit: bool = True,
    ) -> dict[str, Any]:
        """Complete one exact active Feed task for a persisted Review handoff."""

        with write_scope(self.connection, commit=commit):
            updated = self.connection.execute(
                """
                UPDATE study_tasks
                SET status = 'completed', completed_at = ?, updated_at = ?,
                    revision = revision + 1
                WHERE id = ?
                  AND course_id = ?
                  AND source_type = 'review'
                  AND source_id = ?
                  AND status IN ('upcoming', 'overdue')
                  AND revision = ?
                """,
                (
                    completed_at,
                    completed_at,
                    task_id,
                    course_id,
                    review_item_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("active review task changed during completion")
        task = self.get(task_id)
        if task is None:  # pragma: no cover
            raise RuntimeError("completed review task disappeared")
        return task

    def complete(
        self,
        task_id: str,
        *,
        expected_revision: int,
        completed_at: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        timestamp = completed_at or _now()
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """
                UPDATE study_tasks
                SET status = 'completed', completed_at = ?, updated_at = ?,
                    revision = revision + 1
                WHERE id = ? AND status != 'completed' AND revision = ?
                """,
                (timestamp, timestamp, task_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "study task is missing, completed, or updated concurrently"
                )
        task = self.get(task_id)
        if task is None:  # pragma: no cover
            raise RuntimeError("study task disappeared after completion")
        return task

    def snooze(
        self,
        task_id: str,
        *,
        until: str,
        expected_revision: int,
        updated_at: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        timestamp = updated_at or _now()
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """
                UPDATE study_tasks
                SET snoozed_until = ?, updated_at = ?, revision = revision + 1
                WHERE id = ? AND status != 'completed' AND revision = ?
                """,
                (until, timestamp, task_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "study task is missing, completed, or updated concurrently"
                )
        task = self.get(task_id)
        if task is None:  # pragma: no cover
            raise RuntimeError("study task disappeared after snooze")
        return task

    def record_feedback(
        self,
        *,
        feedback_id: str,
        task_id: str,
        feedback_type: str,
        details: dict[str, Any],
        idempotency_key: str,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        existing = self._feedback_by_idempotency_key(idempotency_key)
        if existing is not None:
            expected = {
                "id": feedback_id,
                "task_id": task_id,
                "feedback_type": feedback_type,
                "details": details,
            }
            if any(existing[key] != value for key, value in expected.items()):
                raise ValueError("task feedback idempotency key was reused")
            return existing, False
        timestamp = created_at or _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO study_task_feedback (
                    id, task_id, feedback_type, details_json,
                    idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    task_id,
                    feedback_type,
                    _json(details),
                    idempotency_key,
                    timestamp,
                ),
            )
        feedback = self.get_feedback(feedback_id)
        if feedback is None:  # pragma: no cover
            raise RuntimeError("study task feedback insert did not persist")
        return feedback, True

    def get_feedback(self, feedback_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_task_feedback WHERE id = ?", (feedback_id,)
        ).fetchone()
        return _decode_feedback(row) if row is not None else None

    def _by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT id FROM study_tasks WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return self.get(str(row["id"])) if row is not None else None

    def _feedback_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_task_feedback WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _decode_feedback(row) if row is not None else None

    def _validate_source(
        self,
        *,
        course_id: str,
        concept_id: str | None,
        source_type: str,
        source_id: str | None,
    ) -> None:
        if source_type == "weak_concept":
            expected_id = source_id or concept_id
            if expected_id is None or expected_id != concept_id:
                raise ValueError("weak-concept task must reference its concept")
            row = self.connection.execute(
                "SELECT 1 FROM concepts WHERE id = ? AND course_id = ?",
                (expected_id, course_id),
            ).fetchone()
            if row is None:
                raise ValueError("weak-concept source does not match course")
        elif source_type == "review":
            row = self.connection.execute(
                """
                SELECT 1 FROM review_items
                WHERE id = ? AND course_id = ?
                  AND (? IS NULL OR concept_id = ?)
                """,
                (source_id, course_id, concept_id, concept_id),
            ).fetchone()
            if source_id is None or row is None:
                raise ValueError("review task source does not match course and concept")
        elif source_type == "study_session":
            row = self.connection.execute(
                "SELECT 1 FROM study_sessions WHERE id = ? AND course_id = ?",
                (source_id, course_id),
            ).fetchone()
            if source_id is None or row is None:
                raise ValueError("study-session task source does not match course")
