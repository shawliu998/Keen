"""Immutable outcome lineage for bounded learning-intervention artifacts."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from typing import Any

from . import write_scope


class InterventionOutcomeRepository:
    """Link generated artifacts to later deterministic learner evidence.

    A link means that an artifact was published before the canonical Practice
    for the same Recall branch. It deliberately does not claim the artifact
    caused a later result.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def record_exposure(
        self,
        *,
        course_id: str,
        session_id: str,
        unit_id: str,
        trigger_active_recall_run_id: str,
        intervention_run_id: str,
        intervention_artifact_id: str,
        practice_run_id: str,
        playbook_slug: str,
        playbook_version: int,
        playbook_definition_hash: str,
        linked_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        timestamp = linked_at or datetime.now(UTC).isoformat()
        identity = (
            f"{intervention_run_id}\0{intervention_artifact_id}\0{practice_run_id}"
        )
        lineage_id = (
            "intervention-outcome-"
            + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        )
        values: dict[str, Any] = {
            "id": lineage_id,
            "course_id": course_id,
            "session_id": session_id,
            "unit_id": unit_id,
            "trigger_active_recall_run_id": trigger_active_recall_run_id,
            "intervention_run_id": intervention_run_id,
            "intervention_artifact_id": intervention_artifact_id,
            "practice_run_id": practice_run_id,
            "playbook_slug": playbook_slug,
            "playbook_version": playbook_version,
            "playbook_definition_hash": playbook_definition_hash,
            "linked_at": timestamp,
        }
        columns = tuple(values)
        with write_scope(self.connection, commit=commit):
            existing = self.connection.execute(
                """
                SELECT * FROM learning_intervention_outcomes
                WHERE intervention_run_id = ? AND intervention_artifact_id = ?
                """,
                (intervention_run_id, intervention_artifact_id),
            ).fetchone()
            if existing is not None:
                found = dict(existing)
                if any(
                    found[column] != values[column]
                    for column in columns
                    if column != "linked_at"
                ):
                    raise ValueError("intervention outcome identity was reused")
                return found, False
            self.connection.execute(
                f"""
                INSERT INTO learning_intervention_outcomes ({", ".join(columns)})
                VALUES ({", ".join("?" for _ in columns)})
                """,
                tuple(values[column] for column in columns),
            )
        row = self.connection.execute(
            "SELECT * FROM learning_intervention_outcomes WHERE id = ?",
            (lineage_id,),
        ).fetchone()
        if row is None:  # pragma: no cover - insert above is authoritative
            raise RuntimeError("intervention outcome lineage did not persist")
        return dict(row), True

    def list_published_for_session(
        self, *, course_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        """Return only lineage whose artifact checkpoint was durably published."""

        rows = self.connection.execute(
            """
            SELECT
                lineage.*,
                practice.status AS practice_status,
                practice.answered_at AS practice_answered_at,
                evaluation.correctness AS practice_correctness,
                handoff.review_item_id,
                review_attempt.id AS review_attempt_id,
                review_attempt.rating AS review_rating,
                review_attempt.reviewed_at,
                CAST(
                    json_extract(
                        review_attempt.schedule_before_json,
                        '$.revision'
                    ) AS INTEGER
                ) AS review_revision_before,
                CAST(
                    json_extract(
                        review_attempt.schedule_after_json,
                        '$.revision'
                    ) AS INTEGER
                ) AS review_revision_after
            FROM learning_intervention_outcomes lineage
            JOIN study_practice_runs practice
              ON practice.id = lineage.practice_run_id
            LEFT JOIN answer_evaluations evaluation
              ON evaluation.id = practice.evaluation_id
            LEFT JOIN study_summary_review_handoffs handoff
              ON handoff.practice_run_id = practice.id
            LEFT JOIN review_attempts review_attempt
              ON review_attempt.id = (
                SELECT candidate.id
                FROM review_attempts candidate
                WHERE candidate.review_item_id = handoff.review_item_id
                ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                LIMIT 1
              )
            WHERE lineage.course_id = ? AND lineage.session_id = ?
              AND EXISTS (
                SELECT 1
                FROM agent_events event
                WHERE event.run_id = lineage.intervention_run_id
                  AND event.event_type = 'checkpoint'
                  AND COALESCE(
                        json_extract(event.payload_json, '$.artifactId'),
                        json_extract(event.payload_json, '$.data.artifactId')
                      ) = lineage.intervention_artifact_id
                  AND COALESCE(
                        json_extract(event.payload_json, '$.kind'),
                        json_extract(event.payload_json, '$.data.kind')
                      ) = 'learning_intervention_artifact'
              )
            ORDER BY lineage.linked_at, lineage.id
            """,
            (course_id, session_id),
        ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["InterventionOutcomeRepository"]
