"""Immutable persistence boundary for one active-recall run.

The service composes this ledger with assessment grading and mastery application
inside one transaction.  This repository deliberately does not interpret an
answer or expose idempotency material in returned records.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from . import dump_json, load_json, write_scope


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ActiveRecallRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_run(
        self,
        *,
        run_id: str,
        course_id: str,
        session_id: str,
        unit_id: str,
        checkpoint_id: str,
        assessment_id: str,
        item_id: str,
        concept_id: str,
        mastery_attempts_before: int,
        source_chunk_ids: list[str],
        generator_version: str,
        idempotency_key: str,
        payload_fingerprint: str,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        """Create the pending ledger row, replaying only an identical begin."""

        serialized_sources = dump_json(source_chunk_ids)
        now = created_at or _now()
        with write_scope(self.connection, commit=commit):
            # Read after acquiring the write scope: two same-key callers then
            # serialize into applied + exact replay instead of exposing UNIQUE.
            existing = self._raw_by_begin_key(idempotency_key)
            if existing is not None:
                expected = (
                    course_id,
                    session_id,
                    unit_id,
                    checkpoint_id,
                    assessment_id,
                    item_id,
                    concept_id,
                    mastery_attempts_before,
                    serialized_sources,
                    generator_version,
                    payload_fingerprint,
                )
                actual = tuple(
                    existing[column]
                    for column in (
                        "course_id",
                        "session_id",
                        "unit_id",
                        "checkpoint_id",
                        "assessment_id",
                        "item_id",
                        "concept_id",
                        "mastery_attempts_before",
                        "source_chunk_ids_json",
                        "generator_version",
                        "begin_payload_fingerprint",
                    )
                )
                if actual != expected:
                    raise ValueError("active recall begin idempotency key was reused")
                return self._public(existing), False
            self.connection.execute(
                """
                INSERT INTO study_active_recall_runs (
                    id, course_id, session_id, unit_id, checkpoint_id,
                    assessment_id, item_id, concept_id, mastery_attempts_before,
                    source_chunk_ids_json, generator_version, status, begin_idempotency_key,
                    begin_payload_fingerprint, answer_idempotency_key,
                    answer_payload_fingerprint, attempt_id, evaluation_id,
                    mastery_evidence_id, mastery_event_id, created_at, answered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?,
                          NULL, NULL, NULL, NULL, NULL, NULL, ?, NULL)
                """,
                (
                    run_id,
                    course_id,
                    session_id,
                    unit_id,
                    checkpoint_id,
                    assessment_id,
                    item_id,
                    concept_id,
                    mastery_attempts_before,
                    serialized_sources,
                    generator_version,
                    idempotency_key,
                    payload_fingerprint,
                    now,
                ),
            )
        persisted = self._raw_by_id(run_id)
        if persisted is None:  # pragma: no cover - guarded by INSERT
            raise RuntimeError("active recall run insert did not persist")
        return self._public(persisted), True

    def find_by_begin_idempotency_key(
        self, *, course_id: str, session_id: str, key: str
    ) -> dict[str, Any] | None:
        """Find only a begin replay inside its trusted course/session scope."""

        row = self.connection.execute(
            """
            SELECT * FROM study_active_recall_runs
            WHERE course_id = ? AND session_id = ? AND begin_idempotency_key = ?
            """,
            (course_id, session_id, key),
        ).fetchone()
        row = dict(row) if row is not None else None
        return self._public(row) if row is not None else None

    def find_by_answer_idempotency_key(
        self, *, course_id: str, session_id: str, key: str
    ) -> dict[str, Any] | None:
        """Find only an answer replay inside its trusted course/session scope."""

        row = self.connection.execute(
            """
            SELECT * FROM study_active_recall_runs
            WHERE course_id = ? AND session_id = ? AND answer_idempotency_key = ?
            """,
            (course_id, session_id, key),
        ).fetchone()
        return self._public(dict(row)) if row is not None else None

    def replay_begin(
        self,
        *,
        course_id: str,
        session_id: str,
        idempotency_key: str,
        payload_fingerprint: str,
    ) -> dict[str, Any] | None:
        """Return an exact begin replay without exposing its fingerprint."""

        row = self.connection.execute(
            """
            SELECT * FROM study_active_recall_runs
            WHERE course_id = ? AND session_id = ? AND begin_idempotency_key = ?
            """,
            (course_id, session_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        raw = dict(row)
        if raw["begin_payload_fingerprint"] != payload_fingerprint:
            raise ValueError("active recall begin idempotency key was reused")
        return self._public(raw)

    def replay_answer(
        self,
        *,
        run_id: str,
        course_id: str,
        session_id: str,
        idempotency_key: str,
        payload_fingerprint: str,
    ) -> dict[str, Any] | None:
        """Return an exact sealed answer replay without exposing its proof."""

        row = self.connection.execute(
            """
            SELECT * FROM study_active_recall_runs
            WHERE id = ? AND course_id = ? AND session_id = ?
            """,
            (run_id, course_id, session_id),
        ).fetchone()
        if row is None:
            return None
        raw = dict(row)
        recorded_key = raw["answer_idempotency_key"]
        if recorded_key is None:
            return None
        if (
            recorded_key != idempotency_key
            or raw["answer_payload_fingerprint"] != payload_fingerprint
        ):
            raise ValueError("active recall answer is already recorded")
        return self._public(raw)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._raw_by_id(run_id)
        return self._public(row) if row is not None else None

    def get_run_for_session(
        self, *, course_id: str, session_id: str, run_id: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM study_active_recall_runs
            WHERE id = ? AND course_id = ? AND session_id = ?
            """,
            (run_id, course_id, session_id),
        ).fetchone()
        return self._public(dict(row)) if row is not None else None

    def mark_answered(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        payload_fingerprint: str,
        attempt_id: str,
        evaluation_id: str,
        mastery_evidence_id: str,
        mastery_event_id: int,
        answered_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        """Attach one already-persisted deterministic scoring chain.

        The migration validates all cross-table semantics.  Keeping the update
        narrow lets a service atomically create the attempt/evaluation/evidence/
        event, update the checkpoint and session, then seal this ledger row.
        """

        now = answered_at or _now()
        with write_scope(self.connection, commit=commit):
            # As above, resolve the row only under the writer lock so a second
            # same-key answer observes the sealed row and replays safely.
            existing = self._raw_by_id(run_id)
            if existing is None:
                raise LookupError("active recall run not found")
            if existing["answer_idempotency_key"] is not None:
                expected = (
                    idempotency_key,
                    payload_fingerprint,
                    attempt_id,
                    evaluation_id,
                    mastery_evidence_id,
                    mastery_event_id,
                )
                actual = tuple(
                    existing[column]
                    for column in (
                        "answer_idempotency_key",
                        "answer_payload_fingerprint",
                        "attempt_id",
                        "evaluation_id",
                        "mastery_evidence_id",
                        "mastery_event_id",
                    )
                )
                if actual != expected:
                    raise ValueError("active recall answer is already recorded")
                return self._public(existing), False
            if existing["status"] != "pending":
                raise ValueError("active recall run is not pending")
            key_owner = self._raw_by_answer_key(idempotency_key)
            if key_owner is not None and key_owner["id"] != run_id:
                raise ValueError("active recall answer idempotency key was reused")
            cursor = self.connection.execute(
                """
                UPDATE study_active_recall_runs
                SET status = 'answered', answer_idempotency_key = ?,
                    answer_payload_fingerprint = ?, attempt_id = ?,
                    evaluation_id = ?, mastery_evidence_id = ?,
                    mastery_event_id = ?, answered_at = ?
                WHERE id = ? AND status = 'pending'
                  AND answer_idempotency_key IS NULL
                """,
                (
                    idempotency_key,
                    payload_fingerprint,
                    attempt_id,
                    evaluation_id,
                    mastery_evidence_id,
                    mastery_event_id,
                    now,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("active recall run revision conflict")
        updated = self._raw_by_id(run_id)
        if updated is None:  # pragma: no cover - protected by update
            raise RuntimeError("active recall run disappeared")
        return self._public(updated), True

    def _raw_by_begin_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_active_recall_runs WHERE begin_idempotency_key = ?",
            (key,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _raw_by_id(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_active_recall_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def _raw_by_answer_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_active_recall_runs WHERE answer_idempotency_key = ?",
            (key,),
        ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result["source_chunk_ids"] = load_json(result.pop("source_chunk_ids_json"))
        for column in (
            "begin_idempotency_key",
            "begin_payload_fingerprint",
            "answer_idempotency_key",
            "answer_payload_fingerprint",
        ):
            result.pop(column)
        return result
