"""Read-only, deterministic inputs for the next local learning action.

This service intentionally does not create tasks, sessions, review attempts, or
mastery evidence.  It is a small composition layer over the persisted learning
components so a later coordinator can decide whether an offered action is run.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.planner.feed_priority import (
    FeedCandidate,
    FeedCandidateKind,
    score_feed_candidate,
)
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.misconception_repository import MisconceptionRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.study_repository import StudyRepository
from app.repositories.task_repository import TaskRepository
from app.repository import LearningRepository


_MAX_ITEMS = 50
_VERY_WEAK_MASTERY = 0.35
_WEAK_MASTERY = 0.70

ActionKind = Literal[
    "review_due",
    "resume_study_session",
    "study_very_weak_concept",
    "address_repeated_misconception",
    "study_weak_concept",
]


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


def _minutes(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1440:
        raise ValueError("available_minutes must be an integer between 1 and 1440")
    return value


@dataclass(frozen=True, slots=True)
class LearningPriorityComponent:
    """JSON-friendly immutable copy of one feed-priority contribution."""

    name: str
    raw_value: float
    weight: float
    contribution: float


@dataclass(frozen=True, slots=True)
class LearningActionCandidate:
    """A product action whose rank and explanation never depend on a model."""

    id: str
    action: ActionKind
    target_type: Literal["review_item", "study_session", "concept", "misconception"]
    target_id: str
    concept_id: str | None
    component: str
    priority_tier: int
    estimated_minutes: int
    fits_available_minutes: bool
    priority_score: float
    priority_unclamped_score: float
    priority_algorithm_version: str
    priority_components: tuple[LearningPriorityComponent, ...]
    priority_explanation: tuple[str, ...]
    why: str


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    course_id: str
    as_of: datetime
    available_minutes: int
    course_exists: bool
    due_reviews: tuple[dict[str, Any], ...]
    incomplete_sessions: tuple[dict[str, Any], ...]
    mastery: tuple[dict[str, Any], ...]
    mastery_gaps: tuple[dict[str, Any], ...]
    mastery_gap_count: int
    misconceptions: tuple[dict[str, Any], ...]
    pending_tasks: tuple[dict[str, Any], ...]
    candidates: tuple[LearningActionCandidate, ...]


class LearningSnapshotService:
    """Build a bounded, course-scoped snapshot without mutating SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def build(
        self,
        *,
        course_id: str,
        now: datetime,
        available_minutes: int,
    ) -> LearningSnapshot:
        if not isinstance(course_id, str) or not course_id.strip():
            raise ValueError("course_id must be a non-empty string")
        current_time = _utc(now)
        minutes = _minutes(available_minutes)
        scoped_course_id = course_id.strip()

        owns_read_transaction = not self.connection.in_transaction
        if owns_read_transaction:
            self.connection.execute("BEGIN")
        try:
            return self._build_in_read_transaction(
                course_id=scoped_course_id,
                now=current_time,
                available_minutes=minutes,
            )
        finally:
            if owns_read_transaction and self.connection.in_transaction:
                self.connection.rollback()

    def _build_in_read_transaction(
        self,
        *,
        course_id: str,
        now: datetime,
        available_minutes: int,
    ) -> LearningSnapshot:
        """Read all components from a caller-owned or temporary snapshot."""

        scoped_course_id = course_id
        current_time = now
        minutes = available_minutes
        course_exists = (
            LearningRepository(self.connection).get_course(scoped_course_id) is not None
        )

        # Every read below is course-scoped and capped before candidates are built.
        due_reviews = tuple(
            ReviewRepository(self.connection).list_due(
                due_at=current_time.isoformat(),
                course_id=scoped_course_id,
                limit=_MAX_ITEMS,
            )
        )
        incomplete_sessions = tuple(
            StudyRepository(self.connection).list_incomplete_for_course(
                scoped_course_id, limit=_MAX_ITEMS
            )
        )
        mastery_repository = MasteryRepository(self.connection)
        mastery = tuple(
            mastery_repository.list_for_course(scoped_course_id, limit=_MAX_ITEMS)
        )
        mastery_gaps = tuple(item for item in mastery if item["probability"] is None)
        mastery_gap_count = mastery_repository.count_missing_for_course(
            scoped_course_id
        )
        misconceptions = tuple(
            MisconceptionRepository(self.connection).list_actionable_for_course(
                scoped_course_id, limit=_MAX_ITEMS
            )
        )
        pending_tasks = tuple(
            TaskRepository(self.connection).list_feed(
                as_of=current_time.isoformat(),
                course_id=scoped_course_id,
                limit=_MAX_ITEMS,
            )
        )

        candidates = self._build_candidates(
            now=current_time,
            available_minutes=minutes,
            due_reviews=due_reviews,
            incomplete_sessions=incomplete_sessions,
            mastery=mastery,
            misconceptions=misconceptions,
        )
        return LearningSnapshot(
            course_id=scoped_course_id,
            as_of=current_time,
            available_minutes=minutes,
            course_exists=course_exists,
            due_reviews=due_reviews,
            incomplete_sessions=incomplete_sessions,
            mastery=mastery,
            mastery_gaps=mastery_gaps,
            mastery_gap_count=mastery_gap_count,
            misconceptions=misconceptions,
            pending_tasks=pending_tasks,
            candidates=candidates,
        )

    @staticmethod
    def _build_candidates(
        *,
        now: datetime,
        available_minutes: int,
        due_reviews: tuple[dict[str, Any], ...],
        incomplete_sessions: tuple[dict[str, Any], ...],
        mastery: tuple[dict[str, Any], ...],
        misconceptions: tuple[dict[str, Any], ...],
    ) -> tuple[LearningActionCandidate, ...]:
        records: list[tuple[tuple[object, ...], LearningActionCandidate]] = []
        mastery_by_concept = {
            str(item["concept_id"]): float(item["probability"])
            for item in mastery
            if item["probability"] is not None
        }

        for item in due_reviews:
            due_at = datetime.fromisoformat(str(item["due_at"])).astimezone(UTC)
            records.append(
                LearningSnapshotService._candidate(
                    candidate_id=f"review:{item['id']}",
                    action="review_due",
                    target_type="review_item",
                    target_id=str(item["id"]),
                    concept_id=str(item["concept_id"]),
                    component="review_items",
                    tier=1,
                    estimated_minutes=5,
                    available_minutes=available_minutes,
                    feed_candidate=FeedCandidate(
                        candidate_id=f"review:{item['id']}",
                        kind=FeedCandidateKind.REVIEW,
                        forgetting_risk=1.0,
                        goal_alignment=1.0,
                        estimated_effort_minutes=5,
                        deadline_at=due_at,
                    ),
                    now=now,
                    why=f"Review is due since {due_at.isoformat()}.",
                    sort_key=(1, due_at, str(item["id"])),
                )
            )

        for session in incomplete_sessions:
            effort = int(session["estimated_minutes"])
            status = str(session["status"])
            records.append(
                LearningSnapshotService._candidate(
                    candidate_id=f"session:{session['id']}",
                    action="resume_study_session",
                    target_type="study_session",
                    target_id=str(session["id"]),
                    concept_id=None,
                    component="study_sessions",
                    tier=2,
                    estimated_minutes=effort,
                    available_minutes=available_minutes,
                    feed_candidate=FeedCandidate(
                        candidate_id=f"session:{session['id']}",
                        kind=FeedCandidateKind.STUDY_SESSION,
                        goal_alignment=1.0,
                        estimated_effort_minutes=effort,
                    ),
                    now=now,
                    why=f"Study session is incomplete (status: {status}).",
                    sort_key=(
                        2,
                        0 if status == "paused" else 1,
                        str(session["updated_at"]),
                        str(session["id"]),
                    ),
                )
            )

        for item in mastery:
            if item["probability"] is None:
                continue
            probability = float(item["probability"])
            if probability > _VERY_WEAK_MASTERY:
                continue
            records.append(
                LearningSnapshotService._concept_candidate(
                    item=item,
                    action="study_very_weak_concept",
                    tier=3,
                    now=now,
                    available_minutes=available_minutes,
                    why=(
                        f"Mastery is {probability:.0%}, at or below the "
                        f"very-weak threshold of {_VERY_WEAK_MASTERY:.0%}."
                    ),
                )
            )

        for misconception in misconceptions:
            evidence_count = int(misconception["evidence_count"])
            if evidence_count < 2:
                continue
            concept_id = str(misconception["concept_id"])
            confidence = float(misconception["confidence"])
            records.append(
                LearningSnapshotService._candidate(
                    candidate_id=f"misconception:{misconception['id']}",
                    action="address_repeated_misconception",
                    target_type="misconception",
                    target_id=str(misconception["id"]),
                    concept_id=concept_id,
                    component="misconceptions",
                    tier=4,
                    estimated_minutes=15,
                    available_minutes=available_minutes,
                    feed_candidate=FeedCandidate(
                        candidate_id=f"misconception:{misconception['id']}",
                        kind=FeedCandidateKind.WEAK_CONCEPT,
                        mastery=mastery_by_concept.get(concept_id, 1.0),
                        forgetting_risk=min(1.0, evidence_count / 3),
                        goal_alignment=1.0,
                        estimated_effort_minutes=15,
                    ),
                    now=now,
                    why=(
                        f"Misconception has {evidence_count} evidence records "
                        f"(confidence {confidence:.0%})."
                    ),
                    sort_key=(
                        4,
                        -evidence_count,
                        -confidence,
                        str(misconception["last_seen_at"]),
                        str(misconception["id"]),
                    ),
                )
            )

        for item in mastery:
            if item["probability"] is None:
                continue
            probability = float(item["probability"])
            if not _VERY_WEAK_MASTERY < probability <= _WEAK_MASTERY:
                continue
            records.append(
                LearningSnapshotService._concept_candidate(
                    item=item,
                    action="study_weak_concept",
                    tier=5,
                    now=now,
                    available_minutes=available_minutes,
                    why=f"Mastery is {probability:.0%}, below the weak threshold of {_WEAK_MASTERY:.0%}.",
                )
            )

        records.sort(key=lambda record: record[0])
        return tuple(record[1] for record in records)

    @staticmethod
    def _concept_candidate(
        *,
        item: dict[str, Any],
        action: Literal["study_very_weak_concept", "study_weak_concept"],
        tier: int,
        now: datetime,
        available_minutes: int,
        why: str,
    ) -> tuple[tuple[object, ...], LearningActionCandidate]:
        probability = float(item["probability"])
        concept_id = str(item["concept_id"])
        return LearningSnapshotService._candidate(
            candidate_id=f"concept:{concept_id}:{action}",
            action=action,
            target_type="concept",
            target_id=concept_id,
            concept_id=concept_id,
            component="mastery",
            tier=tier,
            estimated_minutes=15,
            available_minutes=available_minutes,
            feed_candidate=FeedCandidate(
                candidate_id=f"concept:{concept_id}:{action}",
                kind=FeedCandidateKind.WEAK_CONCEPT,
                mastery=probability,
                goal_alignment=1.0,
                estimated_effort_minutes=15,
            ),
            now=now,
            why=why,
            sort_key=(tier, probability, str(item["updated_at"]), concept_id),
        )

    @staticmethod
    def _candidate(
        *,
        candidate_id: str,
        action: ActionKind,
        target_type: Literal[
            "review_item", "study_session", "concept", "misconception"
        ],
        target_id: str,
        concept_id: str | None,
        component: str,
        tier: int,
        estimated_minutes: int,
        available_minutes: int,
        feed_candidate: FeedCandidate,
        now: datetime,
        why: str,
        sort_key: tuple[object, ...],
    ) -> tuple[tuple[object, ...], LearningActionCandidate]:
        priority = score_feed_candidate(feed_candidate, now=now)
        return sort_key, LearningActionCandidate(
            id=candidate_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            concept_id=concept_id,
            component=component,
            priority_tier=tier,
            estimated_minutes=estimated_minutes,
            fits_available_minutes=estimated_minutes <= available_minutes,
            priority_score=priority.score,
            priority_unclamped_score=priority.unclamped_score,
            priority_algorithm_version=priority.algorithm_version,
            priority_components=tuple(
                LearningPriorityComponent(
                    name=component.name,
                    raw_value=component.raw_value,
                    weight=component.weight,
                    contribution=component.contribution,
                )
                for component in priority.components
            ),
            priority_explanation=priority.explanation,
            why=why,
        )
