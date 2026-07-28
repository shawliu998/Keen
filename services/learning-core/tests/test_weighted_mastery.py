from __future__ import annotations

import pytest

from app.mastery import BktParameters, update_bkt
from app.mastery_evidence import (
    DEFAULT_MASTERY_EVIDENCE_PARAMETERS,
    MasteryEvidence,
    MasteryEvidenceParameters,
    ResponseType,
    calculate_evidence_weight,
    update_mastery_from_evidence,
)


def _evidence(**overrides):
    values = {
        "correctness": 1.0,
        "independence": 1.0,
        "hint_level": 0,
        "difficulty": 0.5,
        "confidence": 0.8,
        "response_type": ResponseType.OBJECTIVE,
    }
    values.update(overrides)
    return MasteryEvidence(**values)


def test_weighted_bkt_is_deterministic_traceable_and_clamped():
    first = update_mastery_from_evidence(0.42, _evidence())
    second = update_mastery_from_evidence(0.42, _evidence())

    assert first == second
    assert first.algorithm == "weighted_bkt"
    assert first.algorithm_version == "weighted-bkt/1.0.0"
    assert 0.0 <= first.before <= first.after <= 1.0
    assert 0.0 <= first.evidence_weight <= 1.0
    assert first.after < first.unweighted_target


def test_more_hints_and_less_independence_cannot_increase_evidence_weight():
    weights = [
        calculate_evidence_weight(_evidence(hint_level=level)) for level in range(5)
    ]
    assert weights == sorted(weights, reverse=True)
    assert calculate_evidence_weight(
        _evidence(independence=0.4)
    ) < calculate_evidence_weight(_evidence(independence=1.0))


def test_higher_difficulty_and_confidence_increase_decisive_evidence_weight():
    baseline = calculate_evidence_weight(_evidence(difficulty=0.0, confidence=0.0))
    difficult = calculate_evidence_weight(_evidence(difficulty=1.0, confidence=0.0))
    confident = calculate_evidence_weight(_evidence(difficulty=1.0, confidence=1.0))

    assert baseline < difficult < confident


def test_partial_correctness_is_a_weaker_soft_bkt_observation():
    full = update_mastery_from_evidence(0.42, _evidence(correctness=1.0))
    partial = update_mastery_from_evidence(0.42, _evidence(correctness=0.6))

    assert partial.evidence_weight < full.evidence_weight
    assert partial.after < full.after
    assert 0.0 <= partial.after <= 1.0


def test_user_report_is_auditable_zero_weight_and_does_not_change_mastery():
    result = update_mastery_from_evidence(
        0.42,
        _evidence(response_type=ResponseType.USER_REPORT),
    )

    assert result.evidence_weight == 0.0
    assert result.after == result.before == 0.42


def test_targeted_practice_has_an_explicit_positive_evidence_factor():
    practice = calculate_evidence_weight(_evidence(response_type=ResponseType.PRACTICE))
    objective = calculate_evidence_weight(
        _evidence(response_type=ResponseType.OBJECTIVE)
    )

    assert practice == objective
    assert practice > 0.0


def test_string_response_type_is_normalized_and_unknown_type_is_rejected():
    evidence = _evidence(response_type="objective")
    assert evidence.response_type is ResponseType.OBJECTIVE

    with pytest.raises(ValueError, match="unknown response type"):
        _evidence(response_type="invented")


@pytest.mark.parametrize(
    "field,value",
    [
        ("correctness", -0.1),
        ("independence", 1.1),
        ("difficulty", -1.0),
        ("confidence", 2.0),
        ("hint_level", 5),
    ],
)
def test_mastery_evidence_rejects_out_of_range_inputs(field, value):
    with pytest.raises(ValueError):
        _evidence(**{field: value})


@pytest.mark.parametrize("bad_value", [True, float("nan"), float("inf")])
@pytest.mark.parametrize(
    "field", ["correctness", "independence", "difficulty", "confidence"]
)
def test_mastery_evidence_rejects_boolean_and_non_finite_fields(field, bad_value):
    with pytest.raises(ValueError):
        _evidence(**{field: bad_value})


@pytest.mark.parametrize("bad_value", [True, float("nan"), float("inf")])
@pytest.mark.parametrize(
    "field", ["difficulty_floor", "confidence_floor", "ambiguity_floor"]
)
def test_mastery_parameters_reject_boolean_and_non_finite_floors(field, bad_value):
    with pytest.raises(ValueError):
        MasteryEvidenceParameters(**{field: bad_value})


@pytest.mark.parametrize("bad_value", [True, float("nan"), float("inf")])
def test_mastery_parameters_reject_boolean_and_non_finite_response_factors(
    bad_value,
):
    factors = tuple(
        (response_type, bad_value if response_type is ResponseType.OBJECTIVE else value)
        for response_type, value in DEFAULT_MASTERY_EVIDENCE_PARAMETERS.response_type_factors
    )

    with pytest.raises(ValueError, match="response type factors"):
        MasteryEvidenceParameters(response_type_factors=factors)


@pytest.mark.parametrize("field", ["slip", "guess", "transit"])
@pytest.mark.parametrize("bad_value", [True, float("nan"), float("inf")])
def test_bkt_parameters_reject_boolean_and_non_finite_values(field, bad_value):
    with pytest.raises(ValueError):
        BktParameters(**{field: bad_value})


@pytest.mark.parametrize("prior", [True, float("nan"), float("inf")])
def test_bkt_update_rejects_boolean_and_non_finite_prior(prior):
    with pytest.raises(ValueError, match="prior"):
        update_bkt(prior, correct=True)


@pytest.mark.parametrize("field", ["algorithm", "version"])
@pytest.mark.parametrize("value", ["", "  ", " value "])
def test_mastery_parameters_require_non_empty_trimmed_identifiers(field, value):
    with pytest.raises(ValueError, match="non-empty trimmed string"):
        MasteryEvidenceParameters(**{field: value})
