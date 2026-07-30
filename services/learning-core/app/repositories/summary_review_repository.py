"""Immutable local record linking a study recap to its FSRS review card."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from . import write_scope


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SummaryReviewRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_for_session(
        self, *, course_id: str, session_id: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_summary_review_handoffs WHERE course_id = ? AND session_id = ?",
            (course_id, session_id),
        ).fetchone()
        return dict(row) if row is not None else None

    def replay(
        self,
        *,
        course_id: str,
        session_id: str,
        idempotency_key: str,
        payload_fingerprint: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """SELECT * FROM study_summary_review_handoffs
               WHERE course_id = ? AND session_id = ? AND idempotency_key = ?""",
            (course_id, session_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        value = dict(row)
        if value["payload_fingerprint"] != payload_fingerprint:
            raise ValueError("study summary idempotency key was reused")
        return value

    def create(
        self, *, values: dict[str, Any], commit: bool = True
    ) -> tuple[dict[str, Any], bool]:
        columns = (
            "id",
            "course_id",
            "session_id",
            "unit_id",
            "practice_run_id",
            "assessment_id",
            "item_id",
            "concept_id",
            "review_item_id",
            "active_recall_correct",
            "practice_correct",
            "practice_score",
            "practice_max_score",
            "remaining_units",
            "scheduler_version",
            "review_due_at",
            "review_scheduler",
            "review_state",
            "idempotency_key",
            "originating_task_id",
            "task_completed",
            "payload_fingerprint",
            "created_at",
        )
        with write_scope(self.connection, commit=commit):
            existing = self.connection.execute(
                "SELECT * FROM study_summary_review_handoffs WHERE idempotency_key = ?",
                (values["idempotency_key"],),
            ).fetchone()
            if existing is not None:
                found = dict(existing)
                if any(found[column] != values[column] for column in columns):
                    raise ValueError("study summary idempotency key was reused")
                return found, False
            self.connection.execute(
                f"INSERT INTO study_summary_review_handoffs ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                tuple(values[column] for column in columns),
            )
        row = self.connection.execute(
            "SELECT * FROM study_summary_review_handoffs WHERE id = ?", (values["id"],)
        ).fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError("summary handoff insert did not persist")
        return dict(row), True
