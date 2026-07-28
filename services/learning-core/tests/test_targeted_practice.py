from __future__ import annotations

import pytest

from app.assessment.targeted_practice import (
    TARGETED_PRACTICE_GENERATOR_VERSION,
    TargetedPracticeItem,
    generate_targeted_practice,
)


def test_generates_a_distinct_deterministic_latin_answer_without_leaking_it():
    source = "The chain rule differentiates composite functions."

    first = generate_targeted_practice(
        source, concept="chain rule", excluded_answers=("chain rule",)
    )
    second = generate_targeted_practice(
        source, concept="chain rule", excluded_answers=("CHAIN\\tRULE",)
    )

    assert first == second
    assert first is not None
    assert first.accepted_answer == "differentiates"
    assert first.generator_version == TARGETED_PRACTICE_GENERATOR_VERSION
    assert first.accepted_answer.casefold() not in first.prompt.casefold()
    assert "chain rule" in first.prompt.casefold()


def test_generates_a_distinct_deterministic_cjk_answer_without_leaking_it():
    item = generate_targeted_practice(
        "光合作用将光能转化为化学能。",
        concept="光合作用",
        excluded_answers=("光合作用",),
    )

    assert item is not None
    assert item.accepted_answer != "光合作用"
    assert item.accepted_answer not in item.prompt


@pytest.mark.parametrize(
    "excluded",
    [
        ("  CHAIN\\tRULE ",),
        ["chain rule"],
    ],
)
def test_exclusions_are_nfkc_whitespace_and_casefold_equivalent(excluded):
    item = generate_targeted_practice(
        "The Ｃhain rule differentiates composite functions.",
        concept="Chain rule",
        excluded_answers=excluded,
    )

    assert item is not None
    assert item.accepted_answer.casefold() != "chain rule"


def test_returns_none_when_no_second_safe_candidate_exists():
    assert (
        generate_targeted_practice(
            "Entropy", concept="entropy", excluded_answers=("ENTROPY",)
        )
        is None
    )


@pytest.mark.parametrize(
    "excluded",
    ["entropy", (), ("",), ("entropy", 2)],
)
def test_rejects_invalid_exclusions_without_guessing(excluded):
    assert (
        generate_targeted_practice(
            "Entropy measures disorder.",
            excluded_answers=excluded,  # type: ignore[arg-type]
        )
        is None
    )


def test_output_does_not_include_source_or_concept_fields():
    item = generate_targeted_practice(
        "Photosynthesis converts light energy into chemical energy.",
        concept="photosynthesis",
        excluded_answers=("photosynthesis",),
    )

    assert item is not None
    assert set(item.__dataclass_fields__) == {
        "prompt",
        "accepted_answer",
        "generator_version",
    }
    assert item.accepted_answer.casefold() not in repr(item).casefold()


def test_item_rejects_answer_disclosure_and_unknown_version():
    with pytest.raises(ValueError, match="must not disclose"):
        TargetedPracticeItem(prompt="The answer is entropy.", accepted_answer="entropy")
    with pytest.raises(ValueError, match="generator version"):
        TargetedPracticeItem(
            prompt="Fill [...].",
            accepted_answer="entropy",
            generator_version="targeted-practice/unknown",
        )
