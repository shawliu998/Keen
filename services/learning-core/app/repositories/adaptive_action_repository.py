"""Persistence boundary for deterministic Study Session adaptive actions."""

from __future__ import annotations

import sqlite3
from typing import Any

from . import write_scope


class AdaptiveActionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_action(
        self,
        *,
        action_id: str,
        course_id: str,
        session_id: str,
        unit_id: str,
        predecessor_active_recall_run_id: str,
        predecessor_action_id: str | None,
        kind: str,
        reason_code: str,
        policy_version: str,
        created_at: str,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        with write_scope(self.connection, commit=commit):
            existing = self.connection.execute(
                """SELECT * FROM study_adaptive_actions
                   WHERE predecessor_active_recall_run_id = ? AND kind = ?""",
                (predecessor_active_recall_run_id, kind),
            ).fetchone()
            if existing is not None:
                row = dict(existing)
                expected = (
                    action_id,
                    course_id,
                    session_id,
                    unit_id,
                    predecessor_action_id,
                    reason_code,
                    policy_version,
                )
                actual = tuple(
                    row[column]
                    for column in (
                        "id",
                        "course_id",
                        "session_id",
                        "unit_id",
                        "predecessor_action_id",
                        "reason_code",
                        "policy_version",
                    )
                )
                if actual != expected:
                    raise ValueError("adaptive action identity was reused")
                return self._public(row), False
            self.connection.execute(
                """INSERT INTO study_adaptive_actions (
                       id, course_id, session_id, unit_id,
                       predecessor_active_recall_run_id, predecessor_action_id,
                       kind, reason_code, policy_version, status, revision, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?)""",
                (
                    action_id,
                    course_id,
                    session_id,
                    unit_id,
                    predecessor_active_recall_run_id,
                    predecessor_action_id,
                    kind,
                    reason_code,
                    policy_version,
                    created_at,
                ),
            )
        action = self.get_for_session(
            course_id=course_id, session_id=session_id, action_id=action_id
        )
        if action is None:  # pragma: no cover - guarded by INSERT
            raise RuntimeError("adaptive action insert did not persist")
        return action, True

    def get_for_session(
        self, *, course_id: str, session_id: str, action_id: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """SELECT * FROM study_adaptive_actions
               WHERE id = ? AND course_id = ? AND session_id = ?""",
            (action_id, course_id, session_id),
        ).fetchone()
        return self._public(dict(row)) if row is not None else None

    def get_pending_for_session(
        self, *, course_id: str, session_id: str
    ) -> dict[str, Any] | None:
        rows = self.connection.execute(
            """SELECT * FROM study_adaptive_actions
               WHERE course_id = ? AND session_id = ? AND status = 'pending'
               ORDER BY created_at, id""",
            (course_id, session_id),
        ).fetchall()
        if len(rows) > 1:
            raise RuntimeError("study session has multiple pending adaptive actions")
        return self._public(dict(rows[0])) if rows else None

    def get_for_branch(
        self,
        *,
        course_id: str,
        session_id: str,
        predecessor_active_recall_run_id: str,
        kind: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """SELECT * FROM study_adaptive_actions
               WHERE course_id = ? AND session_id = ?
                 AND predecessor_active_recall_run_id = ? AND kind = ?""",
            (course_id, session_id, predecessor_active_recall_run_id, kind),
        ).fetchone()
        return self._public(dict(row)) if row is not None else None

    def get_by_completion_key(
        self, *, course_id: str, session_id: str, key: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """SELECT * FROM study_adaptive_actions
               WHERE course_id = ? AND session_id = ?
                 AND completion_idempotency_key = ?""",
            (course_id, session_id, key),
        ).fetchone()
        return self._public(dict(row)) if row is not None else None

    def completion_fingerprint(self, action_id: str) -> str | None:
        row = self.connection.execute(
            """SELECT completion_payload_fingerprint
               FROM study_adaptive_actions WHERE id = ?""",
            (action_id,),
        ).fetchone()
        return str(row[0]) if row is not None and row[0] is not None else None

    def branch_identity(self, action_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """SELECT predecessor_active_recall_run_id, predecessor_action_id
               FROM study_adaptive_actions WHERE id = ?""",
            (action_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def complete_remediation(
        self,
        *,
        action_id: str,
        expected_revision: int,
        idempotency_key: str,
        payload_fingerprint: str,
        completed_at: str,
        commit: bool = True,
    ) -> dict[str, Any]:
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """UPDATE study_adaptive_actions
                   SET status = 'completed', revision = revision + 1,
                       completion_idempotency_key = ?,
                       completion_payload_fingerprint = ?,
                       started_at = ?, completed_at = ?
                   WHERE id = ? AND kind = 'remediate' AND status = 'pending'
                     AND revision = ?""",
                (
                    idempotency_key,
                    payload_fingerprint,
                    completed_at,
                    completed_at,
                    action_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("adaptive action revision conflict")
        row = self.connection.execute(
            "SELECT * FROM study_adaptive_actions WHERE id = ?", (action_id,)
        ).fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError("adaptive action disappeared")
        return self._public(dict(row))

    def complete_practice(
        self,
        *,
        action_id: str,
        practice_run_id: str,
        completed_at: str,
        commit: bool = True,
    ) -> dict[str, Any]:
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """UPDATE study_adaptive_actions
                   SET status = 'completed', revision = revision + 1,
                       practice_run_id = ?, started_at = ?, completed_at = ?
                   WHERE id = ? AND kind = 'practice' AND status = 'pending'
                     AND revision = 0""",
                (practice_run_id, completed_at, completed_at, action_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("adaptive practice action revision conflict")
        row = self.connection.execute(
            "SELECT * FROM study_adaptive_actions WHERE id = ?", (action_id,)
        ).fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError("adaptive practice action disappeared")
        return self._public(dict(row))

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: row[key]
            for key in (
                "id",
                "course_id",
                "session_id",
                "unit_id",
                "kind",
                "status",
                "reason_code",
                "policy_version",
                "revision",
                "created_at",
                "started_at",
                "completed_at",
                "cancelled_at",
            )
        }


__all__ = ["AdaptiveActionRepository"]
