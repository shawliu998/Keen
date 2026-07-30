from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.planner.feed_priority import (
    FeedCandidate,
    FeedCandidateKind,
    FeedPriorityWeights,
    rank_feed_candidates,
    score_feed_candidate,
)


NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def _candidate(identifier: str, **changes) -> FeedCandidate:
    values = {"candidate_id": identifier, "kind": FeedCandidateKind.REVIEW}
    values.update(changes)
    return FeedCandidate(**values)


def _raw(result, name: str) -> float:
    return next(item.raw_value for item in result.components if item.name == name)


def test_all_supported_candidate_kinds_are_scored_without_kind_seeds() -> None:
    candidates = [
        _candidate(f"caller-{kind.value}", kind=kind, goal_alignment=0.5)
        for kind in FeedCandidateKind
    ]

    ranked = rank_feed_candidates(candidates, now=NOW)

    assert {item.kind for item in ranked} == set(FeedCandidateKind)
    assert {item.candidate_id for item in ranked} == {
        item.candidate_id for item in candidates
    }


def test_deadline_urgency_has_exact_overdue_now_and_horizon_boundaries() -> None:
    weights = FeedPriorityWeights(deadline_horizon_hours=24.0)
    overdue = score_feed_candidate(
        _candidate("overdue", deadline_at=NOW - timedelta(seconds=1)),
        now=NOW,
        weights=weights,
    )
    due_now = score_feed_candidate(
        _candidate("now", deadline_at=NOW), now=NOW, weights=weights
    )
    halfway = score_feed_candidate(
        _candidate("halfway", deadline_at=NOW + timedelta(hours=12)),
        now=NOW,
        weights=weights,
    )
    horizon = score_feed_candidate(
        _candidate("horizon", deadline_at=NOW + timedelta(hours=24)),
        now=NOW,
        weights=weights,
    )

    assert _raw(overdue, "deadline_urgency") == 1.0
    assert _raw(due_now, "deadline_urgency") == 1.0
    assert _raw(halfway, "deadline_urgency") == 0.5
    assert _raw(horizon, "deadline_urgency") == 0.0


def test_deadline_urgency_uses_real_utc_time_across_dst_fold() -> None:
    new_york = ZoneInfo("America/New_York")
    first_one_thirty = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=0)
    second_one_thirty = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=1)

    result = score_feed_candidate(
        _candidate("fold", deadline_at=second_one_thirty),
        now=first_one_thirty,
        weights=FeedPriorityWeights(deadline_horizon_hours=2.0),
    )

    assert _raw(result, "deadline_urgency") == 0.5
    assert result.deadline_at is second_one_thirty


def test_score_is_bounded_and_effort_is_a_penalty() -> None:
    strong = _candidate(
        "strong",
        deadline_at=NOW,
        forgetting_risk=1.0,
        mastery=0.0,
        prerequisite_importance=1.0,
        goal_alignment=1.0,
    )
    low_effort = score_feed_candidate(strong, now=NOW)
    high_effort = score_feed_candidate(
        _candidate(
            "high-effort",
            deadline_at=NOW,
            forgetting_risk=1.0,
            mastery=0.0,
            prerequisite_importance=1.0,
            goal_alignment=1.0,
            estimated_effort_minutes=120,
        ),
        now=NOW,
    )

    assert low_effort.score == 1.0
    assert 0.0 <= high_effort.score <= 1.0
    assert high_effort.unclamped_score < low_effort.unclamped_score


def test_weights_are_bounded_and_cannot_overweight_positive_signals() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        FeedPriorityWeights(effort_penalty=1.01)
    with pytest.raises(ValueError, match="sum to at most 1"):
        FeedPriorityWeights(goal_alignment=0.21)


def test_priority_breakdown_is_complete_versioned_and_explainable() -> None:
    result = score_feed_candidate(
        _candidate(
            "explain-me",
            forgetting_risk=0.8,
            mastery=0.25,
            prerequisite_importance=0.6,
            goal_alignment=0.9,
            estimated_effort_minutes=30,
        ),
        now=NOW,
    )

    assert [item.name for item in result.components] == [
        "deadline_urgency",
        "forgetting_risk",
        "mastery_weakness",
        "prerequisite_importance",
        "goal_alignment",
        "effort_penalty",
    ]
    assert result.algorithm_version == "feed-priority/1.0.0"
    assert len(result.explanation) == len(result.components)
    assert result.components[-1].contribution < 0.0


def test_ranking_is_stable_with_documented_tie_breaks() -> None:
    candidates = [
        _candidate("z-no-deadline", kind=FeedCandidateKind.MANUAL),
        _candidate("b-later", deadline_at=NOW + timedelta(days=30)),
        _candidate("a-earlier", deadline_at=NOW + timedelta(days=20)),
    ]

    forward = rank_feed_candidates(candidates, now=NOW)
    reverse = rank_feed_candidates(reversed(candidates), now=NOW)

    assert forward == reverse
    assert [item.candidate_id for item in forward] == [
        "a-earlier",
        "b-later",
        "z-no-deadline",
    ]
    assert [item.rank for item in forward] == [1, 2, 3]


def test_deadline_tie_break_uses_real_utc_order_across_dst_fold() -> None:
    new_york = ZoneInfo("America/New_York")
    first_one_thirty = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=0)
    second_one_thirty = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=1)
    weights_without_urgency = FeedPriorityWeights(deadline_urgency=0.0)

    ranked = rank_feed_candidates(
        [
            _candidate("a-later-real-time", deadline_at=second_one_thirty),
            _candidate("z-earlier-real-time", deadline_at=first_one_thirty),
        ],
        now=datetime(2026, 10, 31, 12, 0, tzinfo=new_york),
        weights=weights_without_urgency,
    )

    assert [item.candidate_id for item in ranked] == [
        "z-earlier-real-time",
        "a-later-real-time",
    ]


@pytest.mark.parametrize("value", [-0.01, 1.01, math.nan, math.inf])
def test_unit_interval_inputs_are_bounded_and_finite(value: float) -> None:
    with pytest.raises(ValueError):
        _candidate("invalid", forgetting_risk=value)


def test_timezones_and_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _candidate("naive", deadline_at=datetime(2026, 7, 17))
    with pytest.raises(ValueError, match="timezone-aware"):
        score_feed_candidate(_candidate("valid"), now=datetime(2026, 7, 16))
    with pytest.raises(ValueError, match="unique"):
        rank_feed_candidates([_candidate("same"), _candidate("same")], now=NOW)
