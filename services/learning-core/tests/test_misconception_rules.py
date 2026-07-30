from __future__ import annotations

import math

import pytest

from app.misconceptions import (
    MisconceptionEvidence,
    MisconceptionLabelSource,
    MisconceptionRuleParameters,
    MisconceptionStatusSuggestion,
    infer_misconceptions,
)


def _evidence(number: int, **changes) -> MisconceptionEvidence:
    values = {
        "evidence_id": f"evidence-{number}",
        "concept_id": "concept-derivative",
        "attempt_id": f"attempt-{number}",
        "item_id": f"item-{number}",
        "error_key": "applies-power-rule-to-constant",
    }
    values.update(changes)
    return MisconceptionEvidence(**values)


def test_one_error_never_auto_confirms_even_when_high_confidence() -> None:
    (candidate,) = infer_misconceptions(
        [_evidence(1, response_confidence=1.0, selected_distractor_id="distractor-a")]
    )

    assert candidate.suggested_status is MisconceptionStatusSuggestion.CANDIDATE
    assert candidate.distinct_attempt_count == 1
    assert candidate.high_confidence_error_count == 1
    assert 0.0 <= candidate.confidence < 1.0


def test_repeated_structured_error_moves_from_suspected_to_confirmed() -> None:
    two_attempts = infer_misconceptions([_evidence(1), _evidence(2)])
    three_attempts = infer_misconceptions([_evidence(1), _evidence(2), _evidence(3)])

    assert two_attempts[0].suggested_status is MisconceptionStatusSuggestion.SUSPECTED
    assert three_attempts[0].suggested_status is MisconceptionStatusSuggestion.CONFIRMED
    assert three_attempts[0].repeated_error is True
    assert three_attempts[0].confidence > two_attempts[0].confidence


def test_distractor_and_step_patterns_merge_transitively() -> None:
    candidates = infer_misconceptions(
        [
            _evidence(
                1,
                error_key=None,
                selected_distractor_id="distractor-a",
                failed_step_id="step-chain-rule",
            ),
            _evidence(
                2,
                error_key=None,
                selected_distractor_id="distractor-a",
                failed_step_id=None,
            ),
            _evidence(
                3,
                error_key=None,
                selected_distractor_id=None,
                failed_step_id="step-chain-rule",
            ),
        ]
    )

    assert len(candidates) == 1
    assert candidates[0].repeated_distractor is True
    assert candidates[0].repeated_failed_step is True
    assert candidates[0].evidence_ids == (
        "evidence-1",
        "evidence-2",
        "evidence-3",
    )


def test_model_label_alone_is_not_corroboration() -> None:
    candidates = infer_misconceptions(
        [
            _evidence(
                1,
                error_key=None,
                candidate_label="Constants have derivatives equal to themselves",
                label_source=MisconceptionLabelSource.MODEL,
            ),
            _evidence(
                2,
                error_key=None,
                candidate_label="Constants have derivatives equal to themselves",
                label_source=MisconceptionLabelSource.MODEL,
            ),
        ]
    )

    assert len(candidates) == 2
    assert all(
        item.suggested_status is MisconceptionStatusSuggestion.CANDIDATE
        for item in candidates
    )
    assert all(
        item.label_source is MisconceptionLabelSource.MODEL for item in candidates
    )


def test_explicit_user_confirmation_can_confirm_one_observation() -> None:
    (candidate,) = infer_misconceptions([_evidence(1, user_confirmed=True)])

    assert candidate.suggested_status is MisconceptionStatusSuggestion.CONFIRMED
    assert candidate.user_confirmed is True
    assert candidate.confidence == 1.0


def test_automatic_confidence_is_bounded_and_inputs_must_be_finite() -> None:
    candidate = infer_misconceptions(
        [_evidence(number, response_confidence=1.0) for number in range(1, 20)],
        parameters=MisconceptionRuleParameters(automatic_confidence_cap=0.7),
    )[0]

    assert candidate.confidence == 0.7
    with pytest.raises(ValueError, match="finite"):
        _evidence(20, response_confidence=math.nan)
    with pytest.raises(ValueError, match="unique"):
        infer_misconceptions([_evidence(1), _evidence(1)])


def test_concepts_never_merge_and_output_order_is_stable() -> None:
    first = _evidence(1, concept_id="concept-b")
    second = _evidence(2, concept_id="concept-a")

    forward = infer_misconceptions([first, second])
    reverse = infer_misconceptions([second, first])

    assert forward == reverse
    assert len(forward) == 2
