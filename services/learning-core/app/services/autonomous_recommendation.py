"""Persist one deterministic next learning action from a local snapshot.

This is deliberately a small coordinator, not a second agent runtime.  It
only observes existing local learning state, picks the snapshot's fixed first
candidate, and creates an ordinary study task that the existing feed exposes.
"""

from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any, Literal

from app.concept_bootstrap import ConceptBootstrapRepository, ConceptBootstrapResult
from app.repositories import write_scope
from app.repositories.task_repository import TaskRepository
from app.services.learning_snapshot import (
    LearningActionCandidate,
    LearningSnapshot,
    LearningSnapshotService,
)


_TASK_NAMESPACE = uuid.UUID("49d74b4c-9a9e-42bc-85a2-5d2db1c10548")
RecommendationOutcome = Literal[
    "empty", "task_created", "replay", "covered_by_active_task"
]


@dataclass(frozen=True, slots=True)
class AutonomousRecommendationResult:
    """The verified local result of one observe-and-recommend invocation."""

    outcome: RecommendationOutcome
    course_id: str
    snapshot: LearningSnapshot
    task: dict[str, Any] | None
    candidate: LearningActionCandidate | None
    bootstrap: ConceptBootstrapResult | None

    @property
    def task_created(self) -> bool:
        return self.outcome == "task_created"

    @property
    def replayed(self) -> bool:
        return self.outcome == "replay"

    @property
    def covered_by_active_task(self) -> bool:
        return self.outcome == "covered_by_active_task"


class AutonomousRecommendationCoordinator:
    """Create at most one active, explainable local task for a course target."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def observe_and_recommend(
        self,
        *,
        course_id: str,
        now: datetime,
        available_minutes: int,
        document_id: str | None = None,
    ) -> AutonomousRecommendationResult:
        """Bootstrap an indexed source if asked, then persist the top candidate.

        The snapshot service owns all validation and candidate ordering.  A
        completed task is replayed inside the same UTC day; a later day may
        create a new task only after no active task exists for the candidate.
        Exceptions are intentionally propagated, so callers never receive a
        ``task_created`` result for a transaction that did not commit.
        """

        scoped_course_id = _course_id(course_id)
        current_time = _utc(now)
        minutes = _minutes(available_minutes)
        if document_id is not None and (
            not isinstance(document_id, str) or not document_id.strip()
        ):
            raise ValueError("document_id must be a non-empty string when provided")

        # The observation, coverage check, and task write share one write lock.
        # This prevents two different UTC day-bucket keys from both creating
        # an active task after observing an empty target concurrently.
        with write_scope(self.connection, commit=True):
            bootstrap = None
            if document_id is not None:
                bootstrap = ConceptBootstrapRepository(self.connection).bootstrap(
                    course_id=scoped_course_id,
                    document_id=document_id.strip(),
                    commit=False,
                )

            snapshot = LearningSnapshotService(self.connection).build(
                course_id=scoped_course_id,
                now=current_time,
                available_minutes=minutes,
            )
            if not snapshot.candidates:
                return AutonomousRecommendationResult(
                    outcome="empty",
                    course_id=snapshot.course_id,
                    snapshot=snapshot,
                    task=None,
                    candidate=None,
                    bootstrap=bootstrap,
                )

            candidate = snapshot.candidates[0]
            source_type, source_id, concept_id, extra_components = self._task_source(
                candidate=candidate, snapshot=snapshot
            )
            task_repository = TaskRepository(self.connection)
            active = task_repository.find_active_recommendation(
                course_id=snapshot.course_id,
                source_type=source_type,
                source_id=source_id,
                concept_id=(
                    concept_id
                    if candidate.target_type in {"concept", "misconception"}
                    else None
                ),
            )
            if active is not None:
                return AutonomousRecommendationResult(
                    outcome=(
                        "replay"
                        if _is_same_recommendation(active, candidate.id)
                        else "covered_by_active_task"
                    ),
                    course_id=snapshot.course_id,
                    snapshot=snapshot,
                    task=active,
                    candidate=candidate,
                    bootstrap=bootstrap,
                )

            bucket = current_time.date().isoformat()
            task_id = _task_id(snapshot.course_id, candidate.id, bucket)
            task, created = task_repository.create_task(
                task_id=task_id,
                course_id=snapshot.course_id,
                concept_id=concept_id,
                title=_task_title(candidate, snapshot),
                reason=candidate.why,
                due_at=_day_end(current_time).isoformat(),
                estimated_minutes=candidate.estimated_minutes,
                source_type=source_type,
                source_id=source_id,
                priority_score=candidate.priority_score,
                priority_components={
                    "recommendation_algorithm_version": "autonomous-recommendation/1.0.0",
                    "feed_priority": {
                        "version": candidate.priority_algorithm_version,
                        "components": [
                            {
                                "name": component.name,
                                "raw_value": component.raw_value,
                                "weight": component.weight,
                                "contribution": component.contribution,
                            }
                            for component in candidate.priority_components
                        ],
                        "explanation": list(candidate.priority_explanation),
                        "unclamped_score": candidate.priority_unclamped_score,
                    },
                    "candidate_id": candidate.id,
                    "action": candidate.action,
                    "target_type": candidate.target_type,
                    "target_id": candidate.target_id,
                    "component": candidate.component,
                    "priority_tier": candidate.priority_tier,
                    "priority_score": candidate.priority_score,
                    "estimated_minutes": candidate.estimated_minutes,
                    "available_minutes": snapshot.available_minutes,
                    "fits_available_minutes": candidate.fits_available_minutes,
                    **extra_components,
                },
                recommended_reason=candidate.why,
                scheduled_for=_day_start(current_time).isoformat(),
                idempotency_key=_idempotency_key(
                    snapshot.course_id, candidate.id, bucket
                ),
                created_at=current_time.isoformat(),
                commit=False,
            )
            # Return the authoritative post-write view while the same outer
            # transaction and write lock are still held.  In particular, a
            # newly created task must already be present in pending_tasks.
            updated_snapshot = LearningSnapshotService(self.connection).build(
                course_id=scoped_course_id,
                now=current_time,
                available_minutes=minutes,
            )
            return AutonomousRecommendationResult(
                outcome="task_created" if created else "replay",
                course_id=snapshot.course_id,
                snapshot=updated_snapshot,
                task=task,
                candidate=candidate,
                bootstrap=bootstrap,
            )

    @staticmethod
    def _task_source(
        *, candidate: LearningActionCandidate, snapshot: LearningSnapshot
    ) -> tuple[str, str, str | None, dict[str, str]]:
        if candidate.target_type == "review_item":
            review = next(
                item
                for item in snapshot.due_reviews
                if str(item["id"]) == candidate.target_id
            )
            return "review", candidate.target_id, str(review["concept_id"]), {}
        if candidate.target_type == "study_session":
            return "study_session", candidate.target_id, None, {}
        if candidate.target_type == "concept":
            return "weak_concept", candidate.target_id, candidate.target_id, {}
        if candidate.target_type == "misconception":
            misconception = next(
                item
                for item in snapshot.misconceptions
                if str(item["id"]) == candidate.target_id
            )
            concept_id = str(misconception["concept_id"])
            return (
                "weak_concept",
                concept_id,
                concept_id,
                {"misconception_id": candidate.target_id},
            )
        raise ValueError(
            f"unsupported candidate target type: {candidate.target_type!r}"
        )


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("now must be a timezone-aware UTC datetime")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("now must be UTC")
    return value.astimezone(UTC)


def _course_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("course_id must be a non-empty string")
    return value.strip()


def _minutes(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1440:
        raise ValueError("available_minutes must be an integer between 1 and 1440")
    return value


def _task_id(course_id: str, candidate_id: str, bucket: str) -> str:
    return "recommendation-" + str(
        uuid.uuid5(
            _TASK_NAMESPACE,
            f"{course_id}\N{UNIT SEPARATOR}{candidate_id}\N{UNIT SEPARATOR}{bucket}",
        )
    )


def _idempotency_key(course_id: str, candidate_id: str, bucket: str) -> str:
    return f"autonomous-recommendation/v1:{course_id}:{candidate_id}:{bucket}"


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=UTC)


def _day_end(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.max, tzinfo=UTC)


def _is_same_recommendation(task: dict[str, Any], candidate_id: str) -> bool:
    components = task.get("priority_components")
    return (
        isinstance(components, dict)
        and components.get("recommendation_algorithm_version")
        == "autonomous-recommendation/1.0.0"
        and components.get("candidate_id") == candidate_id
    )


def _task_title(candidate: LearningActionCandidate, snapshot: LearningSnapshot) -> str:
    if candidate.target_type == "review_item":
        review = next(
            item
            for item in snapshot.due_reviews
            if str(item["id"]) == candidate.target_id
        )
        return _title("Review", str(review["prompt"]))
    if candidate.target_type == "study_session":
        session = next(
            item
            for item in snapshot.incomplete_sessions
            if str(item["id"]) == candidate.target_id
        )
        return _title("Resume study session", str(session["title"]))
    if candidate.target_type == "concept":
        mastery = next(
            item
            for item in snapshot.mastery
            if str(item["concept_id"]) == candidate.target_id
        )
        prefix = (
            "Study very weak concept"
            if candidate.action == "study_very_weak_concept"
            else "Study weak concept"
        )
        return _title(prefix, str(mastery["concept_name"]))
    if candidate.target_type == "misconception":
        misconception = next(
            item
            for item in snapshot.misconceptions
            if str(item["id"]) == candidate.target_id
        )
        return _title("Address misconception", str(misconception["label"]))
    raise ValueError(f"unsupported candidate target type: {candidate.target_type!r}")


def _title(prefix: str, label: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", label).split())
    safe_label = normalized[:300] or "learning item"
    return f"{prefix}: {safe_label}"[:500]
