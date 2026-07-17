from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.review.scheduler import Schedule

from . import dump_json, load_json, write_scope


_MAX_SQLITE_INTEGER = (1 << 63) - 1


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return dump_json(value)


def _utc_iso(value: str, *, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a valid ISO 8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")
    return parsed.astimezone(UTC).isoformat()


def _decode_item(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["expected_answer"] = load_json(result.pop("expected_answer_json"))
    result["creation_payload"] = load_json(result.pop("creation_payload_json"))
    if "scheduler_state_json" in result:
        result["scheduler_state"] = load_json(result.pop("scheduler_state_json"))
    return result


def _decode_attempt(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["response"] = load_json(result.pop("response_json"))
    result["schedule_before"] = load_json(result.pop("schedule_before_json"))
    result["schedule_after"] = load_json(result.pop("schedule_after_json"))
    return result


def _schedule_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "difficulty": float(row["difficulty"]),
        "stability": float(row["stability"]),
        "due_at": str(row["due_at"]),
        "last_reviewed_at": row["last_reviewed_at"],
        "repetitions": int(row["repetitions"]),
        "lapses": int(row["lapses"]),
        "state": str(row["state"]),
        "scheduler": str(row["scheduler"]),
        "scheduler_version": str(row["scheduler_version"]),
        "scheduler_state": load_json(row["scheduler_state_json"]),
        "fsrs_card_id": int(row["fsrs_card_id"]),
        "revision": int(row["revision"]),
        "updated_at": str(row["updated_at"]),
    }


class ReviewRepository:
    """Stores FSRS-compatible state without selecting or implementing an algorithm."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_item(
        self,
        *,
        item_id: str,
        course_id: str,
        concept_id: str,
        item_type: str,
        prompt: str,
        expected_answer: Any,
        source_type: str,
        source_id: str | None,
        due_at: str,
        scheduler_version: str,
        idempotency_key: str,
        difficulty: float = 5.0,
        stability: float = 0.0,
        scheduler_state: dict[str, Any] | None = None,
        created_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        if scheduler_state:
            raise ValueError("review scheduler state is assigned internally")
        creation_payload = {
            "id": item_id,
            "course_id": course_id,
            "concept_id": concept_id,
            "item_type": item_type,
            "prompt": prompt,
            "expected_answer": expected_answer,
            "source_type": source_type,
            "source_id": source_id,
            "due_at": due_at,
            "scheduler_version": scheduler_version,
            "difficulty": difficulty,
            "stability": stability,
            "scheduler_state": scheduler_state or {},
        }
        timestamp = _utc_iso(created_at or _now(), field="created_at")
        with write_scope(self.connection, commit=commit):
            existing = self._item_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing["creation_payload"] != creation_payload:
                    raise ValueError("review item idempotency key was reused")
                return existing, False
            self._validate_source(
                course_id=course_id,
                concept_id=concept_id,
                source_type=source_type,
                source_id=source_id,
            )
            fsrs_card_id = self._next_fsrs_card_id()
            initial_schedule = Schedule.from_record(
                {
                    "difficulty": difficulty,
                    "stability": stability,
                    "due_at": due_at,
                    "last_reviewed_at": None,
                    "repetitions": 0,
                    "lapses": 0,
                    "state": "new",
                    "scheduler": "fsrs",
                    "scheduler_version": scheduler_version,
                    "scheduler_state": {"card_id": fsrs_card_id, "step": 0},
                }
            ).to_record()
            self.connection.execute(
                """
                INSERT INTO review_items (
                    id, course_id, concept_id, item_type, prompt,
                    expected_answer_json, source_type, source_id, status,
                    idempotency_key, creation_payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    item_id,
                    course_id,
                    concept_id,
                    item_type,
                    prompt,
                    _json(expected_answer),
                    source_type,
                    source_id,
                    idempotency_key,
                    _json(creation_payload),
                    timestamp,
                    timestamp,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO review_schedules (
                    review_item_id, fsrs_card_id, difficulty, stability, due_at,
                    last_reviewed_at, repetitions, lapses, state, scheduler,
                    scheduler_version, scheduler_state_json, revision, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, 0, 0, 'new', 'fsrs', ?, ?, 0, ?)
                """,
                (
                    item_id,
                    fsrs_card_id,
                    initial_schedule["difficulty"],
                    initial_schedule["stability"],
                    initial_schedule["due_at"],
                    initial_schedule["scheduler_version"],
                    _json(initial_schedule["scheduler_state"]),
                    timestamp,
                ),
            )
        item = self.get_item(item_id)
        if item is None:  # pragma: no cover
            raise RuntimeError("review item insert did not persist")
        return item, True

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT i.*, s.difficulty, s.stability, s.due_at,
                   s.last_reviewed_at, s.repetitions, s.lapses, s.state,
                   s.scheduler, s.scheduler_version, s.scheduler_state_json,
                   s.fsrs_card_id, s.revision,
                   s.updated_at AS schedule_updated_at
            FROM review_items i
            JOIN review_schedules s ON s.review_item_id = i.id
            WHERE i.id = ?
            """,
            (item_id,),
        ).fetchone()
        return _decode_item(row) if row is not None else None

    def list_due(
        self,
        *,
        due_at: str,
        course_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise ValueError("limit must be a positive integer")
        course_clause = " AND i.course_id = ?" if course_id else ""
        parameters: tuple[object, ...] = (due_at, course_id) if course_id else (due_at,)
        limit_clause = " LIMIT ?" if limit is not None else ""
        if limit is not None:
            parameters += (limit,)
        rows = self.connection.execute(
            """
            SELECT i.*, s.difficulty, s.stability, s.due_at,
                   s.last_reviewed_at, s.repetitions, s.lapses, s.state,
                   s.scheduler, s.scheduler_version, s.scheduler_state_json,
                   s.fsrs_card_id, s.revision,
                   s.updated_at AS schedule_updated_at
            FROM review_items i
            JOIN review_schedules s ON s.review_item_id = i.id
            WHERE i.status = 'active' AND s.due_at <= ?
            """
            + course_clause
            + " ORDER BY s.due_at, i.id"
            + limit_clause,
            parameters,
        ).fetchall()
        return [_decode_item(row) for row in rows]

    def record_attempt(
        self,
        *,
        attempt_id: str,
        item_id: str,
        rating: str,
        response: Any,
        idempotency_key: str,
        expected_revision: int,
        difficulty: float,
        stability: float,
        due_at: str,
        repetitions: int,
        lapses: int,
        state: str,
        scheduler_version: str,
        scheduler_state: dict[str, Any],
        reviewed_at: str | None = None,
        commit: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        timestamp = _utc_iso(reviewed_at or _now(), field="reviewed_at")
        with write_scope(self.connection, commit=commit):
            existing = self._attempt_by_idempotency_key(idempotency_key)
            if existing is not None:
                after = existing["schedule_after"]
                expected = {
                    "id": attempt_id,
                    "review_item_id": item_id,
                    "rating": rating,
                    "response": response,
                }
                schedule_expected = {
                    "difficulty": difficulty,
                    "stability": stability,
                    "due_at": due_at,
                    "repetitions": repetitions,
                    "lapses": lapses,
                    "state": state,
                    "scheduler_version": scheduler_version,
                    "scheduler_state": scheduler_state,
                }
                if any(
                    existing[key] != value for key, value in expected.items()
                ) or any(
                    after[key] != value for key, value in schedule_expected.items()
                ):
                    raise ValueError("review attempt idempotency key was reused")
                return existing, False
            schedule = self.connection.execute(
                "SELECT * FROM review_schedules WHERE review_item_id = ?",
                (item_id,),
            ).fetchone()
            if schedule is None:
                raise LookupError("review schedule not found")
            if int(schedule["revision"]) != expected_revision:
                raise ValueError("review schedule was updated concurrently")
            before = _schedule_snapshot(schedule)
            current_schedule = Schedule.from_record(before)
            next_schedule = Schedule.from_record(
                {
                    "difficulty": difficulty,
                    "stability": stability,
                    "due_at": due_at,
                    "last_reviewed_at": timestamp,
                    "repetitions": repetitions,
                    "lapses": lapses,
                    "state": state,
                    "scheduler": "fsrs",
                    "scheduler_version": scheduler_version,
                    "scheduler_state": scheduler_state,
                }
            )
            if next_schedule.scheduler_state["card_id"] != int(
                schedule["fsrs_card_id"]
            ):
                raise ValueError("review schedule FSRS card id cannot change")
            if (
                current_schedule.last_reviewed_at is not None
                and next_schedule.last_reviewed_at < current_schedule.last_reviewed_at
            ):
                raise ValueError("reviewed_at cannot precede the previous review")
            normalized = next_schedule.to_record()
            after = {
                "difficulty": normalized["difficulty"],
                "stability": normalized["stability"],
                "due_at": normalized["due_at"],
                "last_reviewed_at": timestamp,
                "repetitions": normalized["repetitions"],
                "lapses": normalized["lapses"],
                "state": normalized["state"],
                "scheduler": "fsrs",
                "scheduler_version": normalized["scheduler_version"],
                "scheduler_state": normalized["scheduler_state"],
                "fsrs_card_id": int(schedule["fsrs_card_id"]),
                "revision": expected_revision + 1,
                "updated_at": timestamp,
            }
            self.connection.execute(
                """
                INSERT INTO review_attempts (
                    id, review_item_id, rating, response_json,
                    schedule_before_json, schedule_after_json,
                    idempotency_key, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    item_id,
                    rating,
                    _json(response),
                    _json(before),
                    _json(after),
                    idempotency_key,
                    timestamp,
                ),
            )
            updated = self.connection.execute(
                """
                UPDATE review_schedules
                SET difficulty = ?, stability = ?, due_at = ?,
                    last_reviewed_at = ?, repetitions = ?, lapses = ?,
                    state = ?, scheduler = 'fsrs', scheduler_version = ?,
                    scheduler_state_json = ?, revision = revision + 1,
                    updated_at = ?
                WHERE review_item_id = ? AND revision = ?
                """,
                (
                    normalized["difficulty"],
                    normalized["stability"],
                    normalized["due_at"],
                    timestamp,
                    normalized["repetitions"],
                    normalized["lapses"],
                    normalized["state"],
                    normalized["scheduler_version"],
                    _json(normalized["scheduler_state"]),
                    timestamp,
                    item_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("review schedule was updated concurrently")
            self.connection.execute(
                "UPDATE review_items SET updated_at = ? WHERE id = ?",
                (timestamp, item_id),
            )
        attempt = self.get_attempt(attempt_id)
        if attempt is None:  # pragma: no cover
            raise RuntimeError("review attempt insert did not persist")
        return attempt, True

    def get_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM review_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return _decode_attempt(row) if row is not None else None

    def _item_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT id FROM review_items WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return self.get_item(str(row["id"])) if row is not None else None

    def _attempt_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM review_attempts WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _decode_attempt(row) if row is not None else None

    def _next_fsrs_card_id(self) -> int:
        if not self.connection.in_transaction:
            raise RuntimeError("FSRS card id allocation requires a write transaction")
        row = self.connection.execute(
            """
            SELECT next_card_id
            FROM review_fsrs_identity_sequence
            WHERE singleton = 1
            """
        ).fetchone()
        if row is None:
            raise RuntimeError("FSRS card id sequence is unavailable")
        card_id = int(row["next_card_id"])
        if card_id >= _MAX_SQLITE_INTEGER:
            raise OverflowError("FSRS card id space is exhausted")
        updated = self.connection.execute(
            """
            UPDATE review_fsrs_identity_sequence
            SET next_card_id = next_card_id + 1
            WHERE singleton = 1 AND next_card_id = ?
            """,
            (card_id,),
        )
        if updated.rowcount != 1:  # pragma: no cover - writer lock prevents this
            raise RuntimeError("FSRS card id allocation raced unexpectedly")
        return card_id

    def _validate_source(
        self,
        *,
        course_id: str,
        concept_id: str,
        source_type: str,
        source_id: str | None,
    ) -> None:
        if source_id is None:
            if source_type not in {"manual", "agent_recommendation"}:
                raise ValueError("review item source id is required")
            return
        queries = {
            "mastery_evidence": """
                SELECT 1 FROM mastery_evidence e
                JOIN concepts c ON c.id = e.concept_id
                WHERE e.id = ? AND e.concept_id = ? AND c.course_id = ?
            """,
            "misconception": """
                SELECT 1 FROM misconceptions
                WHERE id = ? AND concept_id = ? AND course_id = ?
            """,
            "assessment": """
                SELECT 1 FROM assessments a
                JOIN assessment_items i ON i.assessment_id = a.id
                WHERE a.id = ? AND i.concept_id = ? AND a.course_id = ?
            """,
            "study_session": """
                SELECT 1 FROM study_sessions s
                JOIN concepts c ON c.course_id = s.course_id
                WHERE s.id = ? AND c.id = ? AND s.course_id = ?
            """,
        }
        query = queries.get(source_type)
        if (
            query is not None
            and self.connection.execute(
                query, (source_id, concept_id, course_id)
            ).fetchone()
            is None
        ):
            raise ValueError("review item source does not match course and concept")
