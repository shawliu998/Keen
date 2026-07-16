from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from . import JsonValue, dump_json, load_json, write_scope


class AssessmentItemInput(TypedDict):
    id: str
    item_type: str
    difficulty: str
    prompt: str
    answer_key: JsonValue
    max_score: float
    source_chunk_ids: list[str]
    concept_id: NotRequired[str | None]
    options: NotRequired[list[JsonValue] | None]
    rubric: NotRequired[dict[str, JsonValue] | None]


_ITEM_TYPES = {
    "single_choice",
    "multiple_choice",
    "true_false",
    "short_answer",
    "long_answer",
    "fill_blank",
    "step_by_step",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _string_array(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return value


class AssessmentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_assessment(
        self,
        *,
        assessment_id: str,
        course_id: str,
        title: str,
        purpose: str,
        items: list[AssessmentItemInput],
        session_id: str | None = None,
        commit: bool = True,
    ) -> dict:
        if purpose not in {"diagnostic", "checkpoint", "practice", "quiz", "review"}:
            raise ValueError("invalid assessment purpose")
        if not items:
            raise ValueError("assessment requires at least one item")
        now = _now()
        with write_scope(self.connection, commit=commit):
            self.connection.execute(
                """
                INSERT INTO assessments
                    (id, course_id, session_id, title, purpose, status, revision,
                     created_at, updated_at, published_at)
                VALUES (?, ?, ?, ?, ?, 'draft', 1, ?, ?, NULL)
                """,
                (assessment_id, course_id, session_id, title, purpose, now, now),
            )
            for ordinal, item in enumerate(items):
                item_type = item["item_type"]
                if item_type not in _ITEM_TYPES:
                    raise ValueError("invalid assessment item type")
                options = item.get("options")
                if item_type in {"single_choice", "multiple_choice"} and not options:
                    raise ValueError("choice item requires options")
                rubric = item.get("rubric")
                if rubric is not None and not isinstance(rubric, dict):
                    raise ValueError("rubric must be an object")
                source_ids = _string_array(
                    item["source_chunk_ids"], label="source chunk ids"
                )
                self.connection.execute(
                    """
                    INSERT INTO assessment_items
                        (id, assessment_id, ordinal, concept_id, item_type,
                         difficulty, prompt, options_json, answer_key_json,
                         rubric_json, source_chunk_ids_json, max_score, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"],
                        assessment_id,
                        ordinal,
                        item.get("concept_id"),
                        item_type,
                        item["difficulty"],
                        item["prompt"],
                        dump_json(options) if options is not None else None,
                        dump_json(item["answer_key"]),
                        dump_json(rubric) if rubric is not None else None,
                        dump_json(source_ids),
                        item["max_score"],
                        now,
                    ),
                )
        return self.get_assessment(assessment_id)

    def get_assessment(self, assessment_id: str) -> dict:
        row = self.connection.execute(
            "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
        if row is None:
            raise LookupError("assessment not found")
        result = dict(row)
        items = self.connection.execute(
            "SELECT * FROM assessment_items WHERE assessment_id = ? ORDER BY ordinal",
            (assessment_id,),
        ).fetchall()
        result["items"] = [self._item_dict(item) for item in items]
        return result

    def publish_assessment(
        self,
        assessment_id: str,
        *,
        expected_revision: int,
        commit: bool = True,
    ) -> dict:
        now = _now()
        with write_scope(self.connection, commit=commit):
            assessment = self.connection.execute(
                "SELECT course_id FROM assessments WHERE id = ?", (assessment_id,)
            ).fetchone()
            if assessment is None:
                raise LookupError("assessment not found")
            items = self.connection.execute(
                "SELECT id, concept_id, source_chunk_ids_json FROM assessment_items WHERE assessment_id = ?",
                (assessment_id,),
            ).fetchall()
            if not items:
                raise ValueError("assessment requires at least one item")
            for item in items:
                source_ids = load_json(item["source_chunk_ids_json"])
                if (
                    item["concept_id"] is None
                    or not isinstance(source_ids, list)
                    or not source_ids
                ):
                    raise ValueError(
                        "every published item requires a concept and source chunks"
                    )
                if any(
                    not isinstance(source_id, str) or not source_id
                    for source_id in source_ids
                ):
                    raise ValueError("source chunk ids must be non-empty strings")
                concept = self.connection.execute(
                    "SELECT 1 FROM concepts WHERE id = ? AND course_id = ?",
                    (item["concept_id"], assessment["course_id"]),
                ).fetchone()
                placeholders = ",".join("?" for _ in source_ids)
                source_count = int(
                    self.connection.execute(
                        f"""
                    SELECT COUNT(DISTINCT ch.id) FROM document_chunks ch
                    JOIN course_documents cd ON cd.document_id = ch.document_id
                    WHERE cd.course_id = ? AND ch.id IN ({placeholders})
                    """,
                        (assessment["course_id"], *source_ids),
                    ).fetchone()[0]
                )
                if concept is None or source_count != len(set(source_ids)):
                    raise LookupError(
                        "assessment concept or source chunk is outside the course"
                    )
            cursor = self.connection.execute(
                """
                UPDATE assessments SET status = 'published', published_at = ?,
                    updated_at = ?, revision = revision + 1
                WHERE id = ? AND status = 'draft' AND revision = ?
                """,
                (now, now, assessment_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("assessment revision conflict or invalid status")
        return self.get_assessment(assessment_id)

    def start_attempt(
        self,
        *,
        attempt_id: str,
        assessment_id: str,
        item_id: str,
        answer: JsonValue,
        idempotency_key: str,
        confidence: float | None = None,
        session_id: str | None = None,
        commit: bool = True,
    ) -> dict:
        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        serialized_answer = dump_json(answer)
        now = _now()
        with write_scope(self.connection, commit=commit):
            existing = self.connection.execute(
                "SELECT * FROM assessment_attempts WHERE assessment_id = ? AND idempotency_key = ?",
                (assessment_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                expected = (item_id, session_id, serialized_answer, confidence)
                actual = tuple(
                    existing[key]
                    for key in ("item_id", "session_id", "answer_json", "confidence")
                )
                if actual != expected:
                    raise ValueError(
                        "idempotency key was reused with a different attempt payload"
                    )
                return self.get_attempt(existing["id"])
            assessment = self.connection.execute(
                "SELECT status FROM assessments WHERE id = ?", (assessment_id,)
            ).fetchone()
            if assessment is None:
                raise LookupError("assessment not found")
            if assessment["status"] != "published":
                raise ValueError("assessment is not published")
            self.connection.execute(
                """
                INSERT INTO assessment_attempts
                    (id, assessment_id, item_id, session_id, status,
                     idempotency_key, answer_json, confidence, total_score,
                     max_score, started_at, submitted_at, graded_at, updated_at)
                VALUES (?, ?, ?, ?, 'in_progress', ?, ?, ?, NULL, NULL, ?, NULL, NULL, ?)
                """,
                (
                    attempt_id,
                    assessment_id,
                    item_id,
                    session_id,
                    idempotency_key,
                    serialized_answer,
                    confidence,
                    now,
                    now,
                ),
            )
        return self.get_attempt(attempt_id)

    def get_attempt(self, attempt_id: str) -> dict:
        row = self.connection.execute(
            "SELECT * FROM assessment_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise LookupError("assessment attempt not found")
        result = dict(row)
        result["answer"] = load_json(result.pop("answer_json"))
        return result

    def record_hint(
        self,
        *,
        hint_id: str,
        attempt_id: str,
        item_id: str,
        level: int,
        penalty: float,
        content: str,
        idempotency_key: str,
        commit: bool = True,
    ) -> dict:
        if level not in {1, 2, 3, 4} or penalty < 0:
            raise ValueError("invalid hint level or penalty")
        now = _now()
        with write_scope(self.connection, commit=commit):
            attempt = self.connection.execute(
                "SELECT item_id, status FROM assessment_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
            if attempt is None or attempt["item_id"] != item_id:
                raise LookupError("attempt item not found")
            if attempt["status"] != "in_progress":
                raise ValueError("hints are only available for in-progress attempts")
            existing = self.connection.execute(
                "SELECT * FROM hint_events WHERE attempt_id = ? AND item_id = ? AND idempotency_key = ?",
                (attempt_id, item_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if (existing["level"], existing["penalty"], existing["content"]) != (
                    level,
                    penalty,
                    content,
                ):
                    raise ValueError(
                        "idempotency key was reused with a different hint payload"
                    )
                return dict(existing)
            self.connection.execute(
                """
                INSERT INTO hint_events
                    (id, attempt_id, item_id, level, penalty, content, idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hint_id,
                    attempt_id,
                    item_id,
                    level,
                    penalty,
                    content,
                    idempotency_key,
                    now,
                ),
            )
        return dict(
            self.connection.execute(
                "SELECT * FROM hint_events WHERE id = ?", (hint_id,)
            ).fetchone()
        )

    def grade_attempt(
        self,
        *,
        evaluation_id: str,
        attempt_id: str,
        item_id: str,
        raw_score: float,
        final_score: float,
        correctness: str,
        independence: float,
        rubric_breakdown: dict[str, JsonValue],
        evaluation_source: str,
        feedback: str,
        grader_version: str,
        commit: bool = True,
    ) -> dict:
        if correctness not in {"correct", "incorrect", "partial"}:
            raise ValueError("invalid correctness")
        if evaluation_source not in {"deterministic", "rubric_normalized"}:
            raise ValueError("invalid evaluation source")
        if not 0 <= independence <= 1 or final_score < 0 or raw_score < final_score:
            raise ValueError("invalid score or independence")
        if not isinstance(rubric_breakdown, dict):
            raise ValueError("rubric breakdown must be an object")
        now = _now()
        with write_scope(self.connection, commit=commit):
            existing_evaluation = self.connection.execute(
                "SELECT * FROM answer_evaluations WHERE id = ?", (evaluation_id,)
            ).fetchone()
            if existing_evaluation is not None:
                expected = (
                    attempt_id,
                    item_id,
                    raw_score,
                    final_score,
                    correctness,
                    independence,
                    dump_json(rubric_breakdown),
                    evaluation_source,
                    feedback,
                    grader_version,
                )
                actual = tuple(
                    existing_evaluation[key]
                    for key in (
                        "attempt_id",
                        "item_id",
                        "raw_score",
                        "final_score",
                        "correctness",
                        "independence",
                        "rubric_breakdown_json",
                        "evaluation_source",
                        "feedback",
                        "grader_version",
                    )
                )
                if actual != expected:
                    raise ValueError(
                        "evaluation id was replayed with a different payload"
                    )
                result = dict(existing_evaluation)
                result["answer"] = load_json(result.pop("answer_json"))
                result["rubric_breakdown"] = load_json(
                    result.pop("rubric_breakdown_json")
                )
                return result
            attempt = self.connection.execute(
                """
                SELECT a.item_id, a.status, i.max_score
                FROM assessment_attempts a JOIN assessment_items i ON i.id = a.item_id
                WHERE a.id = ?
                """,
                (attempt_id,),
            ).fetchone()
            if attempt is None or attempt["item_id"] != item_id:
                raise LookupError("attempt item not found")
            if attempt["status"] != "in_progress":
                raise ValueError("only an in-progress attempt can be graded")
            if raw_score > float(attempt["max_score"]):
                raise ValueError("score exceeds item maximum")
            hint_penalty = float(
                self.connection.execute(
                    "SELECT COALESCE(SUM(penalty), 0) FROM hint_events WHERE attempt_id = ? AND item_id = ?",
                    (attempt_id, item_id),
                ).fetchone()[0]
            )
            if max(raw_score - hint_penalty, 0) < final_score:
                raise ValueError("final score does not apply recorded hint penalty")
            is_correct = {"correct": 1, "incorrect": 0, "partial": None}[correctness]
            self.connection.execute(
                """
                INSERT INTO answer_evaluations
                    (id, attempt_id, item_id, answer_json, raw_score, hint_penalty,
                     final_score, is_correct, correctness, score, independence,
                     rubric_breakdown_json, evaluation_source, feedback,
                     evaluator_version, grader_version, created_at)
                SELECT ?, id, item_id, answer_json, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                FROM assessment_attempts WHERE id = ?
                """,
                (
                    evaluation_id,
                    raw_score,
                    hint_penalty,
                    final_score,
                    is_correct,
                    correctness,
                    final_score,
                    independence,
                    dump_json(rubric_breakdown),
                    evaluation_source,
                    feedback,
                    grader_version,
                    grader_version,
                    now,
                    attempt_id,
                ),
            )
            self.connection.execute(
                """
                UPDATE assessment_attempts SET status = 'graded', total_score = ?,
                    max_score = ?, submitted_at = ?, graded_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (final_score, attempt["max_score"], now, now, now, attempt_id),
            )
        evaluation = dict(
            self.connection.execute(
                "SELECT * FROM answer_evaluations WHERE id = ?", (evaluation_id,)
            ).fetchone()
        )
        evaluation["answer"] = load_json(evaluation.pop("answer_json"))
        evaluation["rubric_breakdown"] = load_json(
            evaluation.pop("rubric_breakdown_json")
        )
        return evaluation

    @staticmethod
    def _item_dict(row: sqlite3.Row) -> dict:
        result = dict(row)
        for column in (
            "options_json",
            "answer_key_json",
            "rubric_json",
            "source_chunk_ids_json",
        ):
            value = result.pop(column)
            result[column.removesuffix("_json")] = (
                load_json(value) if value is not None else None
            )
        return result
