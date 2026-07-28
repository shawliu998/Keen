"""Authenticated, deterministic due-review read and rating workflow."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.repositories import write_scope
from app.repositories.review_repository import ReviewRepository
from app.repositories.task_repository import TaskRepository
from app.review import FSRSReviewScheduler, Rating, Schedule

_NAMESPACE = uuid.UUID("f19465db-fdb1-4fd4-8f42-16dca8d66f91")
WriteOutcome = Literal["applied", "replayed"]


class ReviewNotFoundError(LookupError):
    pass


class ReviewConflictError(RuntimeError):
    pass


class ReviewTaskNotFoundError(ReviewNotFoundError):
    """A requested Feed-task handoff no longer has a trusted task."""


class ReviewTaskConflictError(ReviewConflictError):
    """A requested Feed task does not still represent this exact Review item."""


class ReviewIdempotencyConflictError(ReviewConflictError):
    """A replay key was reused with a different persisted Review request."""


@dataclass(frozen=True, slots=True)
class ReviewAttemptResult:
    outcome: WriteOutcome
    attempt: dict[str, Any]


class ReviewSessionService:
    """Schedule review and resolve its Feed task without changing mastery."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.repository = ReviewRepository(connection)

    def list_due(
        self,
        *,
        as_of: datetime,
        course_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        timestamp = _utc(as_of).isoformat()
        items = self.repository.list_due(
            due_at=timestamp,
            course_id=course_id,
            limit=limit,
        )
        return [self._public_item(item) for item in items]

    def record_attempt(
        self,
        *,
        item_id: str,
        rating: str,
        response: str,
        expected_revision: int,
        idempotency_key: str,
        reviewed_at: datetime,
        task_id: str | None = None,
        task_course_id: str | None = None,
    ) -> ReviewAttemptResult:
        repository = self.repository
        if (task_id is None) != (task_course_id is None):
            raise ReviewTaskConflictError("review task context is incomplete")
        stored_response = {"text": response}
        with write_scope(self.connection, commit=True):
            replay = repository.get_attempt_by_idempotency_key(idempotency_key)
            if replay is not None:
                if (
                    replay["review_item_id"] != item_id
                    or replay["rating"] != rating
                    or replay["response"] != stored_response
                    or int(replay["schedule_before"]["revision"]) != expected_revision
                    or replay.get("originating_task_id") != task_id
                ):
                    raise ReviewIdempotencyConflictError(
                        "review idempotency key was reused"
                    )
                if task_id is not None:
                    item = repository.get_item(item_id)
                    if item is None:
                        raise ReviewNotFoundError("review item not found")
                    self._require_task_context(
                        task_id=task_id,
                        task_course_id=task_course_id,
                        item=item,
                        require_active=False,
                    )
                return ReviewAttemptResult("replayed", replay)

            item = repository.get_item(item_id)
            if item is None or item["status"] != "active":
                raise ReviewNotFoundError("review item not found")
            if int(item["revision"]) != expected_revision:
                raise ReviewConflictError("review schedule revision conflict")
            timestamp = _utc(reviewed_at)
            if datetime.fromisoformat(str(item["due_at"])) > timestamp:
                raise ReviewConflictError("review item is not due")
            task = (
                self._require_task_context(
                    task_id=task_id,
                    task_course_id=task_course_id,
                    item=item,
                    require_active=True,
                )
                if task_id is not None
                else None
            )
            try:
                rating_value = Rating(rating)
                scheduled = FSRSReviewScheduler().review(
                    current=Schedule.from_record(item),
                    rating=rating_value,
                    reviewed_at=timestamp,
                )
                schedule = scheduled.to_record()
                attempt, created = repository.record_attempt(
                    attempt_id=(
                        f"review-attempt-{uuid.uuid5(_NAMESPACE, idempotency_key).hex}"
                    ),
                    item_id=item_id,
                    rating=rating_value.value,
                    response=stored_response,
                    idempotency_key=idempotency_key,
                    expected_revision=expected_revision,
                    difficulty=scheduled.difficulty,
                    stability=scheduled.stability,
                    due_at=str(schedule["due_at"]),
                    repetitions=scheduled.repetitions,
                    lapses=scheduled.lapses,
                    state=scheduled.state.value,
                    scheduler_version=scheduled.scheduler_version,
                    scheduler_state=dict(scheduled.scheduler_state),
                    originating_task_id=task_id,
                    reviewed_at=timestamp.isoformat(),
                    commit=False,
                )
            except (TypeError, ValueError) as error:
                raise ReviewConflictError(str(error)) from error
            if created:
                if task is not None:
                    try:
                        TaskRepository(self.connection).complete_active_review_task(
                            task_id=str(task["id"]),
                            course_id=str(item["course_id"]),
                            review_item_id=item_id,
                            expected_revision=int(task["revision"]),
                            completed_at=timestamp.isoformat(),
                            commit=False,
                        )
                    except RuntimeError as error:
                        raise ReviewTaskConflictError(
                            "review task changed during completion"
                        ) from error
        return ReviewAttemptResult("applied" if created else "replayed", attempt)

    def _require_task_context(
        self,
        *,
        task_id: str,
        task_course_id: str | None,
        item: dict[str, Any],
        require_active: bool,
    ) -> dict[str, Any]:
        if not task_course_id:
            raise ReviewTaskConflictError("review task course is required")
        task = TaskRepository(self.connection).get(task_id)
        if task is None:
            raise ReviewTaskNotFoundError("review task not found")
        if (
            task["course_id"] != task_course_id
            or task["course_id"] != item["course_id"]
            or task["source_type"] != "review"
            or task["source_id"] != item["id"]
        ):
            raise ReviewTaskConflictError("review task does not match this review")
        if require_active and task["status"] not in {"upcoming", "overdue"}:
            raise ReviewTaskConflictError("review task is no longer active")
        return task

    def _public_item(self, item: dict[str, Any]) -> dict[str, Any]:
        names = self.connection.execute(
            """SELECT c.title AS course_title, k.name AS concept_name
               FROM courses c JOIN concepts k ON k.course_id = c.id
               WHERE c.id = ? AND k.id = ?""",
            (item["course_id"], item["concept_id"]),
        ).fetchone()
        if names is None:  # protected by foreign keys and course/concept trigger
            raise RuntimeError("review item course lineage is unavailable")
        return {
            "id": item["id"],
            "course_id": item["course_id"],
            "course_title": names["course_title"],
            "concept_id": item["concept_id"],
            "concept_name": names["concept_name"],
            "item_type": item["item_type"],
            "prompt": item["prompt"],
            "expected_answer": item["expected_answer"],
            "source_type": item["source_type"],
            "source_id": item["source_id"],
            "due_at": item["due_at"],
            "state": item["state"],
            "scheduler": item["scheduler"],
            "scheduler_version": item["scheduler_version"],
            "revision": item["revision"],
            "repetitions": item["repetitions"],
            "lapses": item["lapses"],
        }


def public_attempt(result: ReviewAttemptResult) -> dict[str, Any]:
    attempt = result.attempt
    after = attempt["schedule_after"]
    return {
        "outcome": result.outcome,
        "review_item_id": attempt["review_item_id"],
        "rating": attempt["rating"],
        "response": attempt["response"]["text"],
        "reviewed_at": attempt["reviewed_at"],
        "schedule": {
            "due_at": after["due_at"],
            "last_reviewed_at": after["last_reviewed_at"],
            "state": after["state"],
            "scheduler": after["scheduler"],
            "scheduler_version": after["scheduler_version"],
            "revision": after["revision"],
            "repetitions": after["repetitions"],
            "lapses": after["lapses"],
        },
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review timestamp must be timezone-aware")
    return value.astimezone(UTC)
