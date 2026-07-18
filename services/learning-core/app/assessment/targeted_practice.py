"""Deterministic, source-bounded follow-up practice generation.

This generator deliberately returns only the learner-safe prompt and one
server-side answer.  It has no persistence, provider, or random dependency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.assessment import source_cloze


TARGETED_PRACTICE_GENERATOR_VERSION = "targeted-practice/1.0.0"


@dataclass(frozen=True, slots=True)
class TargetedPracticeItem:
    """A learner-safe practice prompt and one hidden accepted answer."""

    prompt: str
    accepted_answer: str = field(repr=False)
    generator_version: str = TARGETED_PRACTICE_GENERATOR_VERSION

    def __post_init__(self) -> None:
        if not self.prompt or len(self.prompt) > source_cloze.MAX_PROMPT_CHARS:
            raise ValueError("targeted practice prompt must be bounded and non-empty")
        if not self.accepted_answer:
            raise ValueError("targeted practice requires one accepted answer")
        if self.generator_version != TARGETED_PRACTICE_GENERATOR_VERSION:
            raise ValueError("targeted practice generator version is not supported")
        if self.accepted_answer.casefold() in self.prompt.casefold():
            raise ValueError("targeted practice prompt must not disclose its answer")


def generate_targeted_practice(
    source: str,
    *,
    concept: str | None = None,
    excluded_answers: Iterable[str] = (),
) -> TargetedPracticeItem | None:
    """Generate one deterministic cloze with an answer outside ``excluded_answers``.

    Exclusions are compared with the same NFKC/whitespace/casefold semantics
    used for candidates.  Returning ``None`` is deliberate when the bounded
    source has no second, unique safe answer.
    """

    normalized_source = source_cloze._normalize_source(source)
    excluded = _normalized_exclusions(excluded_answers)
    if normalized_source is None or excluded is None:
        return None

    candidates: list[str] = []
    concept_candidate = source_cloze._concept_candidate(normalized_source, concept)
    if concept_candidate is not None:
        candidates.append(concept_candidate)
    if not source_cloze._has_repeated_cjk_run(normalized_source):
        candidates.extend(source_cloze._latin_candidates(normalized_source))
        candidates.extend(source_cloze._cjk_candidates(normalized_source))

    answer = _best_allowed_candidate(normalized_source, candidates, excluded)
    if answer is None:
        return None
    prompt = _build_prompt(normalized_source, answer)
    if prompt is None:
        return None
    return TargetedPracticeItem(prompt=prompt, accepted_answer=answer)


def _normalized_exclusions(values: Iterable[str]) -> frozenset[str] | None:
    if isinstance(values, (str, bytes)):
        return None
    try:
        normalized = [source_cloze._normalize_candidate(value) for value in values]
    except TypeError:
        return None
    if not normalized or any(value is None for value in normalized):
        return None
    return frozenset(value.casefold() for value in normalized if value is not None)


def _best_allowed_candidate(
    source: str, candidates: Iterable[str], excluded: frozenset[str]
) -> str | None:
    unique = {
        candidate
        for candidate in candidates
        if source_cloze._is_useful(candidate)
        and source_cloze._is_unique_text(source, candidate)
        and candidate.casefold() not in excluded
    }
    if not unique:
        return None

    def rank(candidate: str) -> tuple[int, int, int, str]:
        is_cjk = source_cloze._contains_cjk(candidate)
        suffix_bonus = int(is_cjk and candidate[-1] in source_cloze._CJK_TERM_SUFFIXES)
        return (
            int(is_cjk) * 2 + suffix_bonus,
            min(len(candidate), 12),
            -source.index(candidate),
            candidate.casefold(),
        )

    return max(unique, key=rank)


def _build_prompt(source: str, answer: str) -> str | None:
    start = source.find(answer)
    if start < 0 or not source_cloze._is_unique_text(source, answer):
        return None
    blanked = source[:start] + source_cloze.BLANK + source[start + len(answer) :]
    prompt = f"Fill in a different missing term using the source context:\n\n{blanked}"
    if (
        len(prompt) > source_cloze.MAX_PROMPT_CHARS
        or answer.casefold() in prompt.casefold()
    ):
        return None
    return prompt
