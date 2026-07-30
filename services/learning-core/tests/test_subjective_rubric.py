from __future__ import annotations

import pytest

from app.assessment.rubric import (
    NormalizedRubricGrade,
    RubricCriterion,
    finalize_subjective_grade,
    normalize_rubric_suggestion,
)


RUBRIC = (
    RubricCriterion("method", max_score=3.0),
    RubricCriterion("result", max_score=2.0),
)


def test_rubric_scores_are_clamped_by_criterion_and_assessment_maximum():
    result = normalize_rubric_suggestion(
        RUBRIC,
        {
            "criterionScores": [
                {"criterionId": "method", "score": 99},
                {"criterionId": "result", "score": -2},
            ],
            "reasoningSummary": "must never be persisted",
            "detectedErrors": ["sign error"],
            "suggestedFeedback": "Check the sign in step two.",
        },
        max_score=2.5,
    )

    assert [(item.criterion_id, item.score) for item in result.criterion_scores] == [
        ("method", 3.0),
        ("result", 0.0),
    ]
    assert (result.raw_score, result.score, result.max_score) == (3.0, 2.5, 2.5)
    assert result.correctness == 1.0
    assert not hasattr(result, "reasoning_summary")
    assert "must never be persisted" not in repr(result)


@pytest.mark.parametrize(
    ("scores", "message"),
    [
        ([{"criterionId": "method", "score": 1}], "missing"),
        (
            [
                {"criterionId": "method", "score": 1},
                {"criterionId": "method", "score": 1},
                {"criterionId": "result", "score": 1},
            ],
            "duplicate",
        ),
        (
            [
                {"criterionId": "method", "score": 1},
                {"criterionId": "invented", "score": 1},
            ],
            "unknown",
        ),
    ],
)
def test_rubric_requires_exactly_the_approved_criteria(scores, message):
    with pytest.raises(ValueError, match=message):
        normalize_rubric_suggestion(RUBRIC, {"criterionScores": scores})


def test_rubric_rejects_non_finite_scores_and_invalid_schema():
    with pytest.raises(ValueError, match="finite"):
        normalize_rubric_suggestion(
            RUBRIC,
            {
                "criterionScores": [
                    {"criterionId": "method", "score": float("nan")},
                    {"criterionId": "result", "score": 1},
                ]
            },
        )


def _normalized_grade(score: float = 4.0):
    return normalize_rubric_suggestion(
        RUBRIC,
        {
            "criterionScores": [
                {"criterionId": "method", "score": min(3.0, max(0.0, score))},
                {
                    "criterionId": "result",
                    "score": min(2.0, max(0.0, score - 3.0)),
                },
            ]
        },
    )


def test_subjective_finalization_without_hint_preserves_independent_score():
    result = finalize_subjective_grade(
        _normalized_grade(), hint_level=0, independence=1.0
    )

    assert (result.raw_score, result.max_score) == (4.0, 5.0)
    assert result.hint_penalty == 0.0
    assert result.final_score == 4.0
    assert result.correctness == 0.8
    assert result.finalizer_version == "subjective-finalizer/1.0.0"
    assert result.hint_policy_version == "hint-penalties/1.0.0"


def test_subjective_finalization_hint_levels_are_monotonic():
    results = [
        finalize_subjective_grade(
            _normalized_grade(), hint_level=level, independence=1.0
        )
        for level in range(5)
    ]

    assert [result.hint_penalty for result in results] == sorted(
        result.hint_penalty for result in results
    )
    assert [result.final_score for result in results] == sorted(
        (result.final_score for result in results), reverse=True
    )


def test_subjective_finalization_applies_independence_before_hint_penalty():
    result = finalize_subjective_grade(
        _normalized_grade(), hint_level=1, independence=0.5
    )

    assert result.raw_score == 4.0
    assert result.hint_penalty == 0.3
    assert result.final_score == 1.7


def test_subjective_finalization_clamps_zero_and_constructed_over_max_score():
    zero = finalize_subjective_grade(
        _normalized_grade(score=0.0), hint_level=4, independence=1.0
    )
    over_max = NormalizedRubricGrade(
        criterion_scores=(),
        raw_score=50.0,
        score=50.0,
        max_score=5.0,
        correctness=1.0,
        detected_errors=(),
        suggested_feedback="",
    )
    capped = finalize_subjective_grade(over_max, hint_level=0, independence=1.0)

    assert (zero.hint_penalty, zero.final_score, zero.correctness) == (0.0, 0.0, 0.0)
    assert (capped.raw_score, capped.final_score, capped.correctness) == (5.0, 5.0, 1.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_score", True),
        ("max_score", float("nan")),
        ("max_score", float("inf")),
        ("min_score", False),
        ("min_score", float("-inf")),
    ],
)
def test_rubric_criterion_rejects_boolean_and_non_finite_bounds(field, value):
    values = {"id": "criterion", "min_score": 0.0, "max_score": 1.0}
    values[field] = value
    with pytest.raises(ValueError):
        RubricCriterion(**values)


@pytest.mark.parametrize("max_score", [True, float("nan"), float("inf")])
def test_rubric_normalization_rejects_boolean_and_non_finite_max(max_score):
    with pytest.raises(ValueError, match="max_score"):
        normalize_rubric_suggestion(
            RUBRIC,
            {
                "criterionScores": [
                    {"criterionId": "method", "score": 1},
                    {"criterionId": "result", "score": 1},
                ]
            },
            max_score=max_score,
        )


@pytest.mark.parametrize("independence", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_subjective_finalization_rejects_invalid_independence(independence):
    with pytest.raises(ValueError, match="independence"):
        finalize_subjective_grade(
            _normalized_grade(), hint_level=0, independence=independence
        )
    with pytest.raises(ValueError, match="detectedErrors"):
        normalize_rubric_suggestion(
            RUBRIC,
            {
                "criterionScores": [
                    {"criterionId": "method", "score": 1},
                    {"criterionId": "result", "score": 1},
                ],
                "detectedErrors": "not-a-list",
            },
        )
