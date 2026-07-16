from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from . import dump_json, load_json, write_scope


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decode_evidence(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["evidence_ids"] = load_json(result.pop("evidence_ids_json"))
    return result


class MasteryRepository:
    """Persists traceable evidence separately from deterministic mastery updates."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def record_evidence(
        self,
        *,
        evidence_id: str,
        concept_id: str,
        evidence_type: str,
        correctness: float,
        independence: float,
        hint_level: int,
        weight: float,
        idempotency_key: str,
        attempt_id: str | None = None,
        session_id: str | None = None,
        confidence_calibration: float | None = None,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        existing = self._evidence_by_idempotency_key(idempotency_key)
        if existing is not None:
            expected = {
                "id": evidence_id,
                "concept_id": concept_id,
                "attempt_id": attempt_id,
                "session_id": session_id,
                "evidence_type": evidence_type,
                "correctness": correctness,
                "independence": independence,
                "hint_level": hint_level,
                "confidence_calibration": confidence_calibration,
                "weight": weight,
            }
            if any(existing[key] != value for key, value in expected.items()):
                raise ValueError("mastery evidence idempotency key was reused")
            return existing, False

        timestamp = created_at or _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO mastery_evidence (
                    id, concept_id, attempt_id, session_id, evidence_type,
                    correctness, independence, hint_level,
                    confidence_calibration, weight, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    concept_id,
                    attempt_id,
                    session_id,
                    evidence_type,
                    correctness,
                    independence,
                    hint_level,
                    confidence_calibration,
                    weight,
                    idempotency_key,
                    timestamp,
                ),
            )
        evidence = self.get_evidence(evidence_id)
        if evidence is None:  # pragma: no cover - protected by the insert
            raise RuntimeError("mastery evidence insert did not persist")
        return evidence, True

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM mastery_evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        return _decode_evidence(row) if row is not None else None

    def list_evidence(self, concept_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM mastery_evidence
            WHERE concept_id = ?
            ORDER BY created_at, id
            """,
            (concept_id,),
        ).fetchall()
        return [_decode_evidence(row) for row in rows]

    def apply_event(
        self,
        *,
        concept_id: str,
        correct: bool,
        probability_before: float,
        probability_after: float,
        algorithm: str,
        algorithm_version: str,
        evidence_ids: list[str],
        idempotency_key: str,
        observed_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        if not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("a mastery event requires unique evidence ids")
        existing = self._event_by_idempotency_key(idempotency_key)
        if existing is not None:
            expected = {
                "concept_id": concept_id,
                "correct": int(correct),
                "probability_before": probability_before,
                "probability_after": probability_after,
                "algorithm": algorithm,
                "algorithm_version": algorithm_version,
                "evidence_ids": evidence_ids,
            }
            if any(existing[key] != value for key, value in expected.items()):
                raise ValueError("mastery event idempotency key was reused")
            return existing, False

        timestamp = observed_at or _now()
        evidence_json = dump_json(evidence_ids)
        with write_scope(self.connection, commit=commit):
            mastery = self.connection.execute(
                "SELECT probability FROM mastery WHERE concept_id = ?",
                (concept_id,),
            ).fetchone()
            if mastery is None:
                raise LookupError("mastery state not found")
            if abs(float(mastery["probability"]) - probability_before) > 0.0000005:
                raise ValueError("mastery probability changed before event application")

            evidence_rows = self.connection.execute(
                f"""
                SELECT id, concept_id FROM mastery_evidence
                WHERE id IN ({",".join("?" for _ in evidence_ids)})
                """,
                evidence_ids,
            ).fetchall()
            if len(evidence_rows) != len(evidence_ids) or any(
                row["concept_id"] != concept_id for row in evidence_rows
            ):
                raise ValueError("mastery event evidence is missing or mismatched")

            cursor = self.connection.execute(
                """
                INSERT INTO mastery_events (
                    concept_id, correct, probability_before, probability_after,
                    observed_at, algorithm, algorithm_version,
                    evidence_ids_json, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    concept_id,
                    int(correct),
                    probability_before,
                    probability_after,
                    timestamp,
                    algorithm,
                    algorithm_version,
                    evidence_json,
                    idempotency_key,
                ),
            )
            self.connection.execute(
                """
                UPDATE mastery
                SET probability = ?, attempts = attempts + 1, updated_at = ?
                WHERE concept_id = ?
                """,
                (probability_after, timestamp, concept_id),
            )
            event_id = int(cursor.lastrowid)
            self.connection.executemany(
                """
                INSERT INTO mastery_event_evidence (event_id, evidence_id)
                VALUES (?, ?)
                """,
                [(event_id, evidence_id) for evidence_id in evidence_ids],
            )
        event = self.get_event(event_id)
        if event is None:  # pragma: no cover - protected by the insert
            raise RuntimeError("mastery event insert did not persist")
        return event, True

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM mastery_events WHERE id = ?", (event_id,)
        ).fetchone()
        return _decode_event(row) if row is not None else None

    def _evidence_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM mastery_evidence WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _decode_evidence(row) if row is not None else None

    def _event_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM mastery_events WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _decode_event(row) if row is not None else None
