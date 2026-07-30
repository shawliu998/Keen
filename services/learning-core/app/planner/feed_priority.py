"""Versioned, explainable, deterministic learning-feed priority scoring."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class FeedCandidateKind(StrEnum):
    REVIEW = "review"
    WEAK_CONCEPT = "weak_concept"
    STUDY_SESSION = "study_session"
    DEADLINE = "deadline"
    MANUAL = "manual"
    AGENT_RECOMMENDATION = "agent_recommendation"


def _finite_number(value: float, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    return numeric


def _unit_interval(value: float, *, field: str) -> float:
    numeric = _finite_number(value, field=field)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return numeric


def _aware(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field} must have a valid UTC offset")
    return value


@dataclass(frozen=True, slots=True)
class FeedPriorityWeights:
    version: str = "feed-priority/1.0.0"
    deadline_urgency: float = 0.25
    forgetting_risk: float = 0.20
    mastery_weakness: float = 0.20
    prerequisite_importance: float = 0.15
    goal_alignment: float = 0.20
    effort_penalty: float = 0.10
    deadline_horizon_hours: float = 168.0
    maximum_effort_minutes: float = 120.0

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")
        for field in (
            "deadline_urgency",
            "forgetting_risk",
            "mastery_weakness",
            "prerequisite_importance",
            "goal_alignment",
            "effort_penalty",
        ):
            _unit_interval(getattr(self, field), field=field)
        positive_weight = sum(
            getattr(self, field)
            for field in (
                "deadline_urgency",
                "forgetting_risk",
                "mastery_weakness",
                "prerequisite_importance",
                "goal_alignment",
            )
        )
        if positive_weight > 1.0 + 1e-12:
            raise ValueError("positive priority weights must sum to at most 1")
        if (
            _finite_number(self.deadline_horizon_hours, field="deadline_horizon_hours")
            <= 0.0
        ):
            raise ValueError("deadline_horizon_hours must be greater than zero")
        if (
            _finite_number(self.maximum_effort_minutes, field="maximum_effort_minutes")
            <= 0.0
        ):
            raise ValueError("maximum_effort_minutes must be greater than zero")


DEFAULT_FEED_PRIORITY_WEIGHTS = FeedPriorityWeights()


@dataclass(frozen=True, slots=True)
class FeedCandidate:
    candidate_id: str
    kind: FeedCandidateKind
    forgetting_risk: float = 0.0
    mastery: float = 1.0
    prerequisite_importance: float = 0.0
    goal_alignment: float = 0.0
    estimated_effort_minutes: float = 0.0
    deadline_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate_id must be a non-empty string")
        object.__setattr__(self, "candidate_id", self.candidate_id.strip())
        try:
            object.__setattr__(self, "kind", FeedCandidateKind(self.kind))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"unsupported feed candidate kind: {self.kind!r}"
            ) from error
        for field in (
            "forgetting_risk",
            "mastery",
            "prerequisite_importance",
            "goal_alignment",
        ):
            object.__setattr__(
                self, field, _unit_interval(getattr(self, field), field=field)
            )
        effort = _finite_number(
            self.estimated_effort_minutes, field="estimated_effort_minutes"
        )
        if effort < 0.0:
            raise ValueError("estimated_effort_minutes must be non-negative")
        object.__setattr__(self, "estimated_effort_minutes", effort)
        if self.deadline_at is not None:
            _aware(self.deadline_at, field="deadline_at")


@dataclass(frozen=True, slots=True)
class PriorityComponent:
    name: str
    raw_value: float
    weight: float
    contribution: float


@dataclass(frozen=True, slots=True)
class FeedPriorityResult:
    candidate_id: str
    kind: FeedCandidateKind
    score: float
    components: tuple[PriorityComponent, ...]
    unclamped_score: float
    explanation: tuple[str, ...]
    algorithm_version: str
    deadline_at: datetime | None
    rank: int | None = None


def _deadline_urgency(
    deadline_at: datetime | None,
    *,
    now: datetime,
    horizon_hours: float,
) -> float:
    if deadline_at is None:
        return 0.0
    remaining = (deadline_at.astimezone(UTC) - now.astimezone(UTC)).total_seconds()
    if remaining <= 0.0:
        return 1.0
    horizon = timedelta(hours=horizon_hours).total_seconds()
    if remaining >= horizon:
        return 0.0
    return 1.0 - remaining / horizon


def score_feed_candidate(
    candidate: FeedCandidate,
    *,
    now: datetime,
    weights: FeedPriorityWeights = DEFAULT_FEED_PRIORITY_WEIGHTS,
) -> FeedPriorityResult:
    """Score one caller-provided candidate without reading external state."""

    current_time = _aware(now, field="now").astimezone(UTC)
    urgency = _deadline_urgency(
        candidate.deadline_at,
        now=current_time,
        horizon_hours=weights.deadline_horizon_hours,
    )
    effort = min(
        1.0, candidate.estimated_effort_minutes / weights.maximum_effort_minutes
    )
    inputs = (
        ("deadline_urgency", urgency, weights.deadline_urgency, 1.0),
        ("forgetting_risk", candidate.forgetting_risk, weights.forgetting_risk, 1.0),
        ("mastery_weakness", 1.0 - candidate.mastery, weights.mastery_weakness, 1.0),
        (
            "prerequisite_importance",
            candidate.prerequisite_importance,
            weights.prerequisite_importance,
            1.0,
        ),
        ("goal_alignment", candidate.goal_alignment, weights.goal_alignment, 1.0),
        ("effort_penalty", effort, weights.effort_penalty, -1.0),
    )
    components = tuple(
        PriorityComponent(
            name=name,
            raw_value=round(raw, 6),
            weight=round(weight, 6),
            contribution=round(raw * weight * sign, 6),
        )
        for name, raw, weight, sign in inputs
    )
    unclamped = sum(component.contribution for component in components)
    score = min(1.0, max(0.0, unclamped))
    explanation = tuple(
        f"{component.name}: {component.raw_value:.3f} × "
        f"{component.weight:.3f} = {component.contribution:+.3f}"
        for component in components
    )
    return FeedPriorityResult(
        candidate_id=candidate.candidate_id,
        kind=candidate.kind,
        score=round(score, 6),
        components=components,
        unclamped_score=round(unclamped, 6),
        explanation=explanation,
        algorithm_version=weights.version,
        deadline_at=candidate.deadline_at,
    )


def rank_feed_candidates(
    candidates: Iterable[FeedCandidate],
    *,
    now: datetime,
    weights: FeedPriorityWeights = DEFAULT_FEED_PRIORITY_WEIGHTS,
) -> tuple[FeedPriorityResult, ...]:
    """Rank candidates with a total ordering independent of input order."""

    current_time = _aware(now, field="now").astimezone(UTC)
    scored = [
        score_feed_candidate(candidate, now=current_time, weights=weights)
        for candidate in candidates
    ]
    identifiers = [item.candidate_id for item in scored]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("candidate_id values must be unique")
    scored.sort(
        key=lambda item: (
            -item.score,
            item.deadline_at is None,
            item.deadline_at.astimezone(UTC)
            if item.deadline_at is not None
            else current_time,
            item.kind.value,
            item.candidate_id,
        )
    )
    return tuple(replace(item, rank=index) for index, item in enumerate(scored, 1))
