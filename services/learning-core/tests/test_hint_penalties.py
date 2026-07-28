from __future__ import annotations

import pytest

from app.assessment.hints import HintLevel, HintParameters, hint_impact


def test_four_hint_levels_have_monotonic_penalty_and_assistance():
    impacts = [hint_impact(level) for level in HintLevel]

    assert [impact.level for impact in impacts[1:]] == [
        HintLevel.DIRECTION,
        HintLevel.KEY_CONCEPT,
        HintLevel.PARTIAL_STEPS,
        HintLevel.NEAR_COMPLETE_SOLUTION,
    ]
    assert [impact.penalty for impact in impacts] == sorted(
        impact.penalty for impact in impacts
    )
    assert [impact.independence for impact in impacts] == sorted(
        (impact.independence for impact in impacts), reverse=True
    )
    assert [impact.evidence_factor for impact in impacts] == sorted(
        (impact.evidence_factor for impact in impacts), reverse=True
    )


def test_hint_parameter_configuration_rejects_non_monotonic_values():
    with pytest.raises(ValueError, match="penalties"):
        HintParameters(penalties=(0.0, 0.2, 0.1, 0.4, 0.5))
    with pytest.raises(ValueError, match="independence"):
        HintParameters(independence=(1.0, 0.8, 0.9, 0.4, 0.2))
    with pytest.raises(ValueError, match="between 0 and 4"):
        hint_impact(5)


@pytest.mark.parametrize("bad_value", [True, float("nan"), float("inf")])
@pytest.mark.parametrize("field", ["penalties", "independence", "evidence_factors"])
def test_hint_parameters_reject_boolean_and_non_finite_values(field, bad_value):
    values = list(getattr(HintParameters(), field))
    values[1] = bad_value

    with pytest.raises(ValueError, match="between 0 and 1"):
        HintParameters(**{field: tuple(values)})


def test_hint_level_rejects_boolean_alias_for_level_one():
    with pytest.raises(ValueError, match="between 0 and 4"):
        hint_impact(True)


@pytest.mark.parametrize("version", ["", "   ", " version/1.0.0 "])
def test_hint_parameters_require_non_empty_trimmed_version(version):
    with pytest.raises(ValueError, match="non-empty trimmed string"):
        HintParameters(version=version)
