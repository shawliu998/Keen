from __future__ import annotations

import pytest

from app.assessment.objective_grading import (
    FillBlankNormalization,
    grade_objective_answer,
)


def test_single_choice_is_exact_and_result_does_not_disclose_answer():
    correct = grade_objective_answer(
        "single_choice", "option-b", "option-b", max_score=2
    )
    incorrect = grade_objective_answer("single_choice", "option-a", "option-b")

    assert (correct.correct, correct.score, correct.max_score) == (True, 2.0, 2.0)
    assert incorrect.correct is False
    assert "expected" not in correct.__dataclass_fields__
    assert "answer" not in repr(correct)


def test_multiple_choice_compares_canonical_sets_and_rejects_duplicates():
    assert grade_objective_answer("multiple_choice", ["c", "a"], ["a", "c"]).correct
    assert not grade_objective_answer("multiple_choice", ["a"], ["a", "c"]).correct

    with pytest.raises(ValueError, match="duplicate"):
        grade_objective_answer("multiple_choice", ["a", "a"], ["a"])


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [({"a": True}, ["a"]), (["a"], {"a": True})],
)
def test_multiple_choice_rejects_mappings_instead_of_grading_their_keys(
    submitted, expected
):
    with pytest.raises(ValueError, match="collection of option identifiers"):
        grade_objective_answer("multiple_choice", submitted, expected)


@pytest.mark.parametrize(
    ("submitted", "expected", "correct"),
    [(True, True, True), (" FALSE ", False, True), ("true", False, False)],
)
def test_true_false_accepts_only_explicit_boolean_forms(submitted, expected, correct):
    assert grade_objective_answer("true_false", submitted, expected).correct is correct


def test_fill_blank_uses_configured_normalization_and_accepted_answers():
    normalized = grade_objective_answer(
        "fill_blank", "  DERIVATIVE\tRULE ", ["chain rule", "derivative rule"]
    )
    exact = grade_objective_answer(
        "fill_blank",
        "NewTon",
        "newton",
        fill_blank_policy=FillBlankNormalization(case_sensitive=True),
    )

    assert normalized.correct is True
    assert exact.correct is False


def test_fill_blank_rejects_mapping_expected_answers_instead_of_grading_keys():
    with pytest.raises(ValueError, match="string or collection of strings"):
        grade_objective_answer("fill_blank", "derivative", {"derivative": True})


@pytest.mark.parametrize("expected", ["", "  ", ["valid", "\t"]])
def test_fill_blank_rejects_empty_accepted_answers_after_normalization(expected):
    with pytest.raises(ValueError, match="cannot be empty"):
        grade_objective_answer("fill_blank", "valid", expected)


@pytest.mark.parametrize(
    "item_type,submitted,expected",
    [
        ("single_choice", "", "a"),
        ("multiple_choice", "a", ["a"]),
        ("true_false", "yes", True),
        ("fill_blank", 42, "42"),
    ],
)
def test_objective_grading_rejects_malformed_answers(item_type, submitted, expected):
    with pytest.raises(ValueError):
        grade_objective_answer(item_type, submitted, expected)


@pytest.mark.parametrize("max_score", [0, -1, float("nan"), float("inf")])
def test_objective_grading_rejects_invalid_max_score(max_score):
    with pytest.raises(ValueError, match="max_score"):
        grade_objective_answer("single_choice", "a", "a", max_score=max_score)
