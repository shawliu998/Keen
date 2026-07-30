"""Bound and normalize model-proposed subjective rubric scores."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Any

from app.assessment.hints import (
    DEFAULT_HINT_PARAMETERS,
    HintLevel,
    HintParameters,
    hint_impact,
)


SUBJECTIVE_FINALIZER_VERSION = "subjective-finalizer/1.0.0"


@dataclass(frozen=True, slots=True)
class RubricCriterion:
    id: str
    max_score: float
    min_score: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("criterion id cannot be empty")
        for name, value in (
            ("min_score", self.min_score),
            ("max_score", self.max_score),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"criterion {name} must be numeric")
        if not isfinite(self.min_score) or not isfinite(self.max_score):
            raise ValueError("criterion score bounds must be finite")
        if self.min_score < 0.0:
            raise ValueError("criterion min_score cannot be negative")
        if self.max_score <= self.min_score:
            raise ValueError("criterion max_score must exceed min_score")


@dataclass(frozen=True, slots=True)
class CriterionScore:
    criterion_id: str
    score: float


@dataclass(frozen=True, slots=True)
class NormalizedRubricGrade:
    criterion_scores: tuple[CriterionScore, ...]
    raw_score: float
    score: float
    max_score: float
    correctness: float
    detected_errors: tuple[str, ...]
    suggested_feedback: str
    grader_version: str = "subjective-rubric/1.0.0"


@dataclass(frozen=True, slots=True)
class FinalizedSubjectiveGrade:
    """Final score derived only from normalized rubric and assistance policy."""

    raw_score: float
    max_score: float
    independence: float
    hint_level: HintLevel
    hint_penalty: float
    final_score: float
    correctness: float
    finalizer_version: str
    hint_policy_version: str


def _finite_number(value: Any, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    return numeric


def normalize_rubric_suggestion(
    criteria: Sequence[RubricCriterion],
    suggestion: Mapping[str, Any],
    *,
    max_score: float | None = None,
) -> NormalizedRubricGrade:
    """Normalize an untrusted grader suggestion to an approved rubric.

    ``reasoningSummary`` is intentionally ignored and absent from the returned
    object so hidden or free-form reasoning cannot enter persistence.
    """

    if not criteria:
        raise ValueError("rubric must contain at least one criterion")
    if not isinstance(suggestion, Mapping):
        raise ValueError("rubric suggestion must be an object")
    criterion_by_id = {criterion.id: criterion for criterion in criteria}
    if len(criterion_by_id) != len(criteria):
        raise ValueError("rubric criterion ids must be unique")

    proposed = suggestion.get("criterionScores")
    if isinstance(proposed, (str, bytes)) or not isinstance(proposed, Sequence):
        raise ValueError("criterionScores must be a list")

    raw_by_id: dict[str, float] = {}
    for entry in proposed:
        if not isinstance(entry, Mapping):
            raise ValueError("each criterion score must be an object")
        criterion_id = entry.get("criterionId", entry.get("criterion_id"))
        if not isinstance(criterion_id, str) or criterion_id not in criterion_by_id:
            raise ValueError(f"unknown rubric criterion: {criterion_id!r}")
        if criterion_id in raw_by_id:
            raise ValueError(f"duplicate rubric criterion: {criterion_id!r}")
        raw_by_id[criterion_id] = _finite_number(
            entry.get("score"), field=f"score for {criterion_id}"
        )

    missing = set(criterion_by_id).difference(raw_by_id)
    if missing:
        raise ValueError(f"missing rubric criteria: {sorted(missing)!r}")

    normalized_scores = tuple(
        CriterionScore(
            criterion_id=criterion.id,
            score=min(
                criterion.max_score,
                max(criterion.min_score, raw_by_id[criterion.id]),
            ),
        )
        for criterion in criteria
    )
    rubric_max = sum(criterion.max_score for criterion in criteria)
    approved_max = (
        rubric_max
        if max_score is None
        else min(rubric_max, _finite_number(max_score, field="max_score"))
    )
    if approved_max <= 0.0:
        raise ValueError("max_score must be positive")
    raw_score = sum(item.score for item in normalized_scores)
    final_score = min(approved_max, max(0.0, raw_score))

    errors = suggestion.get("detectedErrors", ())
    if isinstance(errors, (str, bytes)) or not isinstance(errors, Sequence):
        raise ValueError("detectedErrors must be a list of strings")
    if any(not isinstance(error, str) for error in errors):
        raise ValueError("detectedErrors must be a list of strings")
    feedback = suggestion.get("suggestedFeedback", "")
    if not isinstance(feedback, str):
        raise ValueError("suggestedFeedback must be a string")

    return NormalizedRubricGrade(
        criterion_scores=normalized_scores,
        raw_score=round(raw_score, 6),
        score=round(final_score, 6),
        max_score=round(approved_max, 6),
        correctness=round(min(1.0, max(0.0, final_score / approved_max)), 6),
        detected_errors=tuple(errors),
        suggested_feedback=feedback,
    )


def finalize_subjective_grade(
    normalized_grade: NormalizedRubricGrade,
    *,
    hint_level: HintLevel | int,
    independence: float,
    hint_parameters: HintParameters = DEFAULT_HINT_PARAMETERS,
) -> FinalizedSubjectiveGrade:
    """Apply independence and versioned hint penalty to a normalized score.

    No final-score argument is accepted.  The final value is always derived
    from the already bounded rubric result and then clamped to its maximum.
    ``hint_penalty`` is the number of score points deducted after applying
    independence, rather than an opaque model-provided value.
    """

    if not isinstance(normalized_grade, NormalizedRubricGrade):
        raise ValueError("normalized_grade must be a normalized rubric result")
    normalized_independence = _finite_number(independence, field="independence")
    if not 0.0 <= normalized_independence <= 1.0:
        raise ValueError("independence must be between 0 and 1")

    impact = hint_impact(hint_level, hint_parameters)
    approved_max = _finite_number(
        normalized_grade.max_score, field="normalized max_score"
    )
    if approved_max <= 0.0:
        raise ValueError("normalized max_score must be positive")
    raw_score = min(
        approved_max,
        max(0.0, _finite_number(normalized_grade.score, field="normalized score")),
    )
    independent_score = raw_score * normalized_independence
    penalty_points = independent_score * impact.penalty
    final_score = independent_score - penalty_points

    return FinalizedSubjectiveGrade(
        raw_score=round(raw_score, 6),
        max_score=round(approved_max, 6),
        independence=round(normalized_independence, 6),
        hint_level=impact.level,
        hint_penalty=round(min(approved_max, max(0.0, penalty_points)), 6),
        final_score=round(min(approved_max, max(0.0, final_score)), 6),
        correctness=round(
            min(1.0, max(0.0, final_score / approved_max)),
            6,
        ),
        finalizer_version=SUBJECTIVE_FINALIZER_VERSION,
        hint_policy_version=impact.version,
    )
