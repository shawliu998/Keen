from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .mastery import BktParameters, update_bkt


def _dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


class LearningRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_courses(self) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT c.id, c.title, c.description, c.created_at,
                   COUNT(DISTINCT concepts.id) AS concept_count,
                   ROUND(AVG(mastery.probability), 6) AS average_mastery
            FROM courses c
            LEFT JOIN concepts ON concepts.course_id = c.id
            LEFT JOIN mastery ON mastery.concept_id = concepts.id
            GROUP BY c.id
            ORDER BY c.created_at, c.id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_course(self, course_id: str) -> dict | None:
        return _dict(
            self.connection.execute(
                "SELECT id, title, description, created_at FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()
        )

    def list_tasks(
        self, *, course_id: str | None = None, status: str | None = None
    ) -> list[dict]:
        clauses: list[str] = []
        parameters: list[str] = []
        if course_id:
            clauses.append("t.course_id = ?")
            parameters.append(course_id)
        if status:
            clauses.append("t.status = ?")
            parameters.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute(
            """
            SELECT t.id, t.course_id, c.title AS course_title, t.title, t.reason,
                   t.due_at, t.estimated_minutes, t.status, t.concept_id,
                   t.created_at, t.updated_at
            FROM study_tasks t JOIN courses c ON c.id = t.course_id
            """
            + where
            + " ORDER BY t.due_at, t.id",
            parameters,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: str) -> dict | None:
        return _dict(
            self.connection.execute(
                """
                SELECT id, course_id, title, reason, due_at, estimated_minutes,
                       status, concept_id, created_at, updated_at
                FROM study_tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        )

    def create_task(
        self,
        *,
        task_id: str,
        course_id: str,
        concept_id: str | None,
        title: str,
        reason: str,
        due_at: str,
        estimated_minutes: int,
    ) -> dict | None:
        if self.get_course(course_id) is None:
            return None
        if concept_id is not None:
            matching_concept = self.connection.execute(
                "SELECT 1 FROM concepts WHERE id = ? AND course_id = ?",
                (concept_id, course_id),
            ).fetchone()
            if matching_concept is None:
                raise LookupError("concept not found in course")
        now = datetime.now(UTC).isoformat()
        self.connection.execute(
            """
            INSERT INTO study_tasks
                (id, course_id, concept_id, title, reason, due_at,
                 estimated_minutes, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'upcoming', ?, ?)
            """,
            (
                task_id,
                course_id,
                concept_id,
                title,
                reason,
                due_at,
                estimated_minutes,
                now,
                now,
            ),
        )
        self.connection.commit()
        return self.get_task(task_id)

    def update_task(
        self, task_id: str, *, status: str | None, due_at: str | None
    ) -> dict | None:
        if self.get_task(task_id) is None:
            return None
        fields: list[str] = []
        parameters: list[str] = []
        if status is not None:
            fields.append("status = ?")
            parameters.append(status)
        if due_at is not None:
            fields.append("due_at = ?")
            parameters.append(due_at)
        if fields:
            fields.append("updated_at = ?")
            parameters.append(datetime.now(UTC).isoformat())
            parameters.append(task_id)
            self.connection.execute(
                f"UPDATE study_tasks SET {', '.join(fields)} WHERE id = ?", parameters
            )
            self.connection.commit()
        return self.get_task(task_id)

    def list_mastery(self, *, course_id: str | None = None) -> list[dict]:
        where = " WHERE c.course_id = ?" if course_id else ""
        parameters = (course_id,) if course_id else ()
        rows = self.connection.execute(
            """
            SELECT c.id AS concept_id, c.course_id, c.name AS concept_name,
                   m.probability, m.attempts, m.updated_at
            FROM concepts c JOIN mastery m ON m.concept_id = c.id
            """
            + where
            + " ORDER BY c.course_id, c.name",
            parameters,
        ).fetchall()
        return [dict(row) for row in rows]

    def record_attempt(self, concept_id: str, *, correct: bool) -> dict | None:
        row = self.connection.execute(
            """
            SELECT c.id, c.bkt_slip, c.bkt_guess, c.bkt_transit,
                   m.probability, m.attempts
            FROM concepts c JOIN mastery m ON m.concept_id = c.id
            WHERE c.id = ?
            """,
            (concept_id,),
        ).fetchone()
        if row is None:
            return None
        previous = float(row["probability"])
        probability = update_bkt(
            previous,
            correct=correct,
            parameters=BktParameters(
                slip=float(row["bkt_slip"]),
                guess=float(row["bkt_guess"]),
                transit=float(row["bkt_transit"]),
            ),
        )
        observed_at = datetime.now(UTC).isoformat()
        self.connection.execute(
            """
            UPDATE mastery
            SET probability = ?, attempts = attempts + 1, updated_at = ?
            WHERE concept_id = ?
            """,
            (probability, observed_at, concept_id),
        )
        self.connection.execute(
            """
            INSERT INTO mastery_events
                (concept_id, correct, probability_before, probability_after, observed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (concept_id, int(correct), previous, probability, observed_at),
        )
        self.connection.commit()
        return {
            "concept_id": concept_id,
            "correct": correct,
            "probability_before": previous,
            "probability_after": probability,
            "attempts": int(row["attempts"]) + 1,
            "updated_at": observed_at,
        }
