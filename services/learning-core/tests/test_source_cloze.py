from __future__ import annotations

import pytest

from app.assessment.source_cloze import (
    MAX_PROMPT_CHARS,
    MAX_SOURCE_CHARS,
    SOURCE_CLOZE_GENERATOR_VERSION,
    SourceClozeItem,
    generate_source_cloze,
)


def test_prefers_a_unique_whole_normalized_concept_and_hides_answer():
    item = generate_source_cloze(
        "  The chain\trule differentiates composite functions.  ",
        concept="chain rule",
    )

    assert item is not None
    assert item.accepted_answers == ("chain rule",)
    assert item.generator_version == SOURCE_CLOZE_GENERATOR_VERSION
    assert "chain rule" not in item.prompt.casefold()
    assert "[...]" in item.prompt
    assert len(item.prompt) <= MAX_PROMPT_CHARS


def test_concept_must_be_a_whole_unique_source_occurrence():
    partial = generate_source_cloze("Concatenate values carefully.", concept="cat")
    repeated = generate_source_cloze(
        "Entropy measures disorder; entropy changes.", concept="entropy"
    )

    assert partial is not None
    assert partial.accepted_answers != ("cat",)
    assert repeated is not None
    assert repeated.accepted_answers != ("entropy",)


@pytest.mark.parametrize(
    "source,concept",
    [
        ("", None),
        ("x" * (MAX_SOURCE_CHARS + 1), None),
        ("safe\x00 source", None),
        ("https://example.test/lesson", None),
        ("123456", None),
        ("the and of", None),
        ("an", None),
        ("概", None),
        ("https://example.test", "https://example.test"),
    ],
)
def test_rejects_empty_oversize_control_url_numeric_common_and_tiny_material(
    source, concept
):
    assert generate_source_cloze(source, concept=concept) is None


def test_latin_fallback_is_deterministic_and_derived_from_source():
    source = "Photosynthesis converts light energy into chemical energy."

    first = generate_source_cloze(source)
    second = generate_source_cloze(source)

    assert first == second
    assert first is not None
    assert first.accepted_answers == ("Photosynthesis",)
    assert first.accepted_answers[0].casefold() not in first.prompt.casefold()


def test_fallback_skips_a_repeated_highest_candidate_for_a_unique_lower_candidate():
    item = generate_source_cloze("Photosynthesis photosynthesis converts light energy.")

    assert item is not None
    assert item.accepted_answers == ("converts",)


def test_casefold_expansion_before_answer_does_not_misplace_the_blank():
    item = generate_source_cloze("Straße energy becomes useful work.", concept="energy")

    assert item is not None
    assert item.accepted_answers == ("energy",)
    assert "Straße [...] becomes useful work." in item.prompt
    assert "energy" not in item.prompt.casefold()


def test_cjk_fallback_is_deterministic_and_derived_from_source():
    source = "光合作用将光能转化为化学能。"

    item = generate_source_cloze(source)

    assert item is not None
    assert item.accepted_answers == ("光合作用",)
    assert item.accepted_answers[0] not in item.prompt


def test_repeated_ambiguous_fallback_has_no_item():
    assert generate_source_cloze("entropy entropy") is None
    assert generate_source_cloze("光合作用光合作用") is None


def test_item_cannot_disclose_hidden_accepted_answer():
    with pytest.raises(ValueError, match="must not disclose"):
        SourceClozeItem(prompt="The answer is entropy.", accepted_answers=("entropy",))


def test_item_rejects_unknown_generator_version():
    with pytest.raises(ValueError, match="generator version"):
        SourceClozeItem(
            prompt="The answer is [...].",
            accepted_answers=("entropy",),
            generator_version="source-cloze/unknown",
        )
