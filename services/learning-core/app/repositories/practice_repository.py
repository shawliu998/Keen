"""Immutable persistence boundary for one targeted-practice run."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from . import dump_json, load_json, write_scope


def _now() -> str:
    return datetime.now(UTC).isoformat()


def practice_source_content_fingerprint(
    *, unit_content: str, chunks: list[tuple[str, str]]
) -> str:
    """Seal the exact unit excerpt and cited chunk contents in stable order."""

    canonical = dump_json(
        {
            "unit_content": unit_content,
            "chunks": [
                {"id": chunk_id, "content": content}
                for chunk_id, content in sorted(chunks)
            ],
        }
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


class PracticeRepository:
    """Persist only the sealed practice ledger; grading stays in the service."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_run(
        self,
        *,
        run_id: str,
        course_id: str,
        session_id: str,
        unit_id: str,
        predecessor_active_recall_run_id: str,
        checkpoint_id: str,
        assessment_id: str,
        item_id: str,
        concept_id: str,
        mastery_attempts_before: int,
        source_chunk_ids: list[str],
        source_content_fingerprint: str,
        accepted_answers_fingerprint: str,
        generator_version: str,
        idempotency_key: str,
        payload_fingerprint: str,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        """Create a pending run, replaying only byte-for-byte equivalent begin data."""

        sources = dump_json(source_chunk_ids)
        now = created_at or _now()
        with write_scope(self.connection, commit=commit):
            existing = self._raw_by_begin_key(idempotency_key)
            if existing is not None:
                expected = (
                    course_id,
                    session_id,
                    unit_id,
                    predecessor_active_recall_run_id,
                    checkpoint_id,
                    assessment_id,
                    item_id,
                    concept_id,
                    mastery_attempts_before,
                    sources,
                    source_content_fingerprint,
                    accepted_answers_fingerprint,
                    generator_version,
                    payload_fingerprint,
                )
                actual = tuple(
                    existing[column]
                    for column in (
                        "course_id",
                        "session_id",
                        "unit_id",
                        "predecessor_active_recall_run_id",
                        "checkpoint_id",
                        "assessment_id",
                        "item_id",
                        "concept_id",
                        "mastery_attempts_before",
                        "source_chunk_ids_json",
                        "source_content_fingerprint",
                        "accepted_answers_fingerprint",
                        "generator_version",
                        "begin_payload_fingerprint",
                    )
                )
                if actual != expected:
                    raise ValueError("practice begin idempotency key was reused")
                return self._public(existing), False
            self.connection.execute(
                """
                INSERT INTO study_practice_runs (
                    id, course_id, session_id, unit_id, predecessor_active_recall_run_id,
                    checkpoint_id, assessment_id, item_id, concept_id, mastery_attempts_before,
                    source_chunk_ids_json, source_content_fingerprint,
                    accepted_answers_fingerprint, generator_version, status,
                    begin_idempotency_key, begin_payload_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    run_id,
                    course_id,
                    session_id,
                    unit_id,
                    predecessor_active_recall_run_id,
                    checkpoint_id,
                    assessment_id,
                    item_id,
                    concept_id,
                    mastery_attempts_before,
                    sources,
                    source_content_fingerprint,
                    accepted_answers_fingerprint,
                    generator_version,
                    idempotency_key,
                    payload_fingerprint,
                    now,
                ),
            )
        row = self._raw_by_id(run_id)
        if row is None:  # pragma: no cover - INSERT guarded above
            raise RuntimeError("practice run insert did not persist")
        return self._public(row), True

    def find_by_begin_idempotency_key(
        self, *, course_id: str, session_id: str, key: str
    ) -> dict[str, Any] | None:
        return self._find_scoped("begin_idempotency_key", course_id, session_id, key)

    def find_by_answer_idempotency_key(
        self, *, course_id: str, session_id: str, key: str
    ) -> dict[str, Any] | None:
        return self._find_scoped("answer_idempotency_key", course_id, session_id, key)

    def replay_begin(
        self,
        *,
        course_id: str,
        session_id: str,
        idempotency_key: str,
        payload_fingerprint: str,
    ) -> dict[str, Any] | None:
        row = self._scoped_raw(
            "begin_idempotency_key", course_id, session_id, idempotency_key
        )
        if row is None:
            return None
        if row["begin_payload_fingerprint"] != payload_fingerprint:
            raise ValueError("practice begin idempotency key was reused")
        return self._public(row)

    def replay_answer(
        self,
        *,
        run_id: str,
        course_id: str,
        session_id: str,
        idempotency_key: str,
        payload_fingerprint: str,
    ) -> dict[str, Any] | None:
        row = self._raw_for_session(run_id, course_id, session_id)
        if row is None or row["answer_idempotency_key"] is None:
            return None
        if (row["answer_idempotency_key"], row["answer_payload_fingerprint"]) != (
            idempotency_key,
            payload_fingerprint,
        ):
            raise ValueError("practice answer is already recorded")
        return self._public(row)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._raw_by_id(run_id)
        return self._public(row) if row is not None else None

    def get_run_for_session(
        self, *, course_id: str, session_id: str, run_id: str
    ) -> dict[str, Any] | None:
        row = self._raw_for_session(run_id, course_id, session_id)
        return self._public(row) if row is not None else None

    def get_run_for_predecessor(
        self,
        *,
        course_id: str,
        session_id: str,
        predecessor_active_recall_run_id: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """SELECT * FROM study_practice_runs
               WHERE course_id = ? AND session_id = ?
                 AND predecessor_active_recall_run_id = ?""",
            (course_id, session_id, predecessor_active_recall_run_id),
        ).fetchone()
        return self._public(dict(row)) if row is not None else None

    def get_only_run_for_session(
        self, *, course_id: str, session_id: str
    ) -> dict[str, Any] | None:
        rows = self.connection.execute(
            """SELECT * FROM study_practice_runs
               WHERE course_id = ? AND session_id = ? ORDER BY created_at, id""",
            (course_id, session_id),
        ).fetchall()
        if len(rows) > 1:
            raise RuntimeError("study session has multiple practice runs")
        return self._public(dict(rows[0])) if rows else None

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
        """Seal an already-persisted attempt/evaluation/evidence/event graph."""

        now = answered_at or _now()
        with write_scope(self.connection, commit=commit):
            existing = self._raw_by_id(run_id)
            if existing is None:
                raise LookupError("practice run not found")
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
                    raise ValueError("practice answer is already recorded")
                return self._public(existing), False
            if existing["status"] != "pending":
                raise ValueError("practice run is not pending")
            owner = self._raw_by_answer_key(idempotency_key)
            if owner is not None and owner["id"] != run_id:
                raise ValueError("practice answer idempotency key was reused")
            cursor = self.connection.execute(
                """
                UPDATE study_practice_runs SET status = 'answered', answer_idempotency_key = ?,
                    answer_payload_fingerprint = ?, attempt_id = ?, evaluation_id = ?,
                    mastery_evidence_id = ?, mastery_event_id = ?, answered_at = ?
                WHERE id = ? AND status = 'pending' AND answer_idempotency_key IS NULL
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
                raise RuntimeError("practice run revision conflict")
        row = self._raw_by_id(run_id)
        if row is None:  # pragma: no cover
            raise RuntimeError("practice run disappeared")
        return self._public(row), True

    def cancel_terminal_runs(
        self, *, session_id: str, status: str, cancelled_at: str, commit: bool = True
    ) -> int:
        """Service helper for explicit terminalization; DB trigger is the backstop."""

        if status not in {"cancelled", "failed"}:
            raise ValueError("terminal status must be cancelled or failed")
        reason = f"session_{status}"
        with write_scope(self.connection, commit=commit):
            cursor = self.connection.execute(
                """UPDATE study_practice_runs SET status = 'cancelled', cancelled_at = ?,
                   cancellation_reason = ? WHERE session_id = ? AND status = 'pending'""",
                (cancelled_at, reason, session_id),
            )
        return cursor.rowcount

    def _find_scoped(
        self, column: str, course_id: str, session_id: str, key: str
    ) -> dict[str, Any] | None:
        row = self._scoped_raw(column, course_id, session_id, key)
        return self._public(row) if row is not None else None

    def _scoped_raw(
        self, column: str, course_id: str, session_id: str, key: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT * FROM study_practice_runs WHERE course_id = ? AND session_id = ? AND {column} = ?",
            (course_id, session_id, key),
        ).fetchone()
        return dict(row) if row is not None else None

    def _raw_for_session(
        self, run_id: str, course_id: str, session_id: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_practice_runs WHERE id = ? AND course_id = ? AND session_id = ?",
            (run_id, course_id, session_id),
        ).fetchone()
        return dict(row) if row is not None else None

    def _raw_by_id(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_practice_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def _raw_by_begin_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_practice_runs WHERE begin_idempotency_key = ?", (key,)
        ).fetchone()
        return dict(row) if row is not None else None

    def _raw_by_answer_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM study_practice_runs WHERE answer_idempotency_key = ?", (key,)
        ).fetchone()
        return dict(row) if row is not None else None

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        """Project a run only after proving hidden answer and source seals."""

        item = self.connection.execute(
            "SELECT answer_key_json FROM assessment_items WHERE id = ?",
            (row["item_id"],),
        ).fetchone()
        if item is None:  # protected by RESTRICT FK; keeps corruption fail-closed
            raise RuntimeError("practice item disappeared")
        canonical_answer_key = dump_json(load_json(str(item["answer_key_json"])))
        fingerprint = sha256(canonical_answer_key.encode("utf-8")).hexdigest()
        if fingerprint != row["accepted_answers_fingerprint"]:
            raise RuntimeError(
                "practice accepted answers fingerprint does not match item"
            )
        source_ids = load_json(row["source_chunk_ids_json"])
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or any(not isinstance(value, str) or not value for value in source_ids)
            or len(set(source_ids)) != len(source_ids)
        ):
            raise RuntimeError("practice source seal is malformed")
        unit = self.connection.execute(
            "SELECT content FROM study_units WHERE id = ?", (row["unit_id"],)
        ).fetchone()
        placeholders = ",".join("?" for _ in source_ids)
        chunks = self.connection.execute(
            f"""SELECT DISTINCT ch.id, ch.content FROM document_chunks ch
                JOIN course_documents cd ON cd.document_id = ch.document_id
                WHERE cd.course_id = ? AND ch.id IN ({placeholders})""",
            (row["course_id"], *source_ids),
        ).fetchall()
        if unit is None or {chunk["id"] for chunk in chunks} != set(source_ids):
            raise RuntimeError("practice cited source is unavailable")
        source_fingerprint = practice_source_content_fingerprint(
            unit_content=str(unit["content"]),
            chunks=[(str(chunk["id"]), str(chunk["content"])) for chunk in chunks],
        )
        if source_fingerprint != row["source_content_fingerprint"]:
            raise RuntimeError(
                "practice source content fingerprint does not match source"
            )
        result = dict(row)
        result["source_chunk_ids"] = source_ids
        result.pop("source_chunk_ids_json")
        for column in (
            "source_content_fingerprint",
            "accepted_answers_fingerprint",
            "begin_idempotency_key",
            "begin_payload_fingerprint",
            "answer_idempotency_key",
            "answer_payload_fingerprint",
        ):
            result.pop(column)
        return result
