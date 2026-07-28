"""Deterministic, source-bounded cloze generation for active recall.

This module deliberately has no persistence, provider, or random dependency.
It only creates an item when a single safe answer can be derived from the
provided source.  Callers must keep ``accepted_answers`` server-side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata


MAX_SOURCE_CHARS = 1200
MAX_PROMPT_CHARS = 1400
BLANK = "[...]"
SOURCE_CLOZE_GENERATOR_VERSION = "source-cloze/1.0.0"

_WHITESPACE = re.compile(r"\s+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_COMMON_TERMS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "与",
        "一个",
        "及",
        "在",
        "多",
        "是",
        "有",
        "和",
        "或",
        "我们",
        "的",
        "了",
    }
)
_CJK_TERM_SUFFIXES = frozenset(
    {
        "值",
        "力",
        "化",
        "器",
        "学",
        "定",
        "度",
        "律",
        "性",
        "态",
        "效",
        "数",
        "法",
        "理",
        "率",
        "用",
        "的",
        "系",
        "能",
        "量",
    }
)


@dataclass(frozen=True, slots=True)
class SourceClozeItem:
    """A learner-safe prompt plus server-only expected-answer material."""

    prompt: str
    accepted_answers: tuple[str, ...] = field(repr=False)
    generator_version: str = SOURCE_CLOZE_GENERATOR_VERSION

    def __post_init__(self) -> None:
        if not self.prompt or len(self.prompt) > MAX_PROMPT_CHARS:
            raise ValueError("source cloze prompt must be bounded and non-empty")
        if len(self.accepted_answers) != 1 or not self.accepted_answers[0]:
            raise ValueError("source cloze requires exactly one accepted answer")
        if self.generator_version != SOURCE_CLOZE_GENERATOR_VERSION:
            raise ValueError("source cloze generator version is not supported")
        answer = self.accepted_answers[0]
        if answer.casefold() in self.prompt.casefold():
            raise ValueError("source cloze prompt must not disclose its answer")


def generate_source_cloze(
    source: str, *, concept: str | None = None
) -> SourceClozeItem | None:
    """Create one bounded cloze, or ``None`` when no safe answer exists.

    An exact, useful, single-occurrence concept wins.  Otherwise the function
    selects one unique Latin word or CJK phrase from the source with stable
    tie-breaking.  Invalid, ambiguous, or unsafe material deliberately yields
    no item instead of guessing.
    """

    normalized_source = _normalize_source(source)
    if normalized_source is None:
        return None

    answer = _concept_candidate(normalized_source, concept)
    if answer is None:
        answer = _fallback_candidate(normalized_source)
    if answer is None:
        return None

    prompt = _build_prompt(normalized_source, answer)
    if prompt is None:
        return None
    return SourceClozeItem(prompt=prompt, accepted_answers=(answer,))


def _normalize_source(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_SOURCE_CHARS:
        return None
    if any(
        unicodedata.category(character).startswith("C") and not character.isspace()
        for character in value
    ):
        return None
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()
    if not normalized or len(normalized) > MAX_SOURCE_CHARS or _URL.search(normalized):
        return None
    return normalized


def _concept_candidate(source: str, concept: object) -> str | None:
    if concept is None:
        return None
    normalized = _normalize_candidate(concept)
    if normalized is None or not _is_useful(normalized):
        return None
    starts = _whole_occurrences(source, normalized)
    if len(starts) != 1 or not _is_unique_text(source, normalized):
        return None
    return source[starts[0] : starts[0] + len(normalized)]


def _fallback_candidate(source: str) -> str | None:
    if _has_repeated_cjk_run(source):
        return None
    candidates = [
        candidate
        for candidate in (*_latin_candidates(source), *_cjk_candidates(source))
        if _is_useful(candidate) and _is_unique_text(source, candidate)
    ]
    if not candidates:
        return None

    def rank(candidate: str) -> tuple[int, int, int, str]:
        is_cjk = _contains_cjk(candidate)
        suffix_bonus = int(is_cjk and candidate[-1] in _CJK_TERM_SUFFIXES)
        return (
            int(is_cjk) * 2 + suffix_bonus,
            min(len(candidate), 12),
            -source.index(candidate),
            candidate.casefold(),
        )

    return max(candidates, key=rank)


def _normalize_candidate(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()
    if not normalized or len(normalized) > 80:
        return None
    if any(
        unicodedata.category(character).startswith("C") and not character.isspace()
        for character in normalized
    ):
        return None
    return normalized


def _is_useful(candidate: str) -> bool:
    folded = candidate.casefold()
    if folded in _COMMON_TERMS or _URL.fullmatch(candidate) or candidate.isnumeric():
        return False
    if not any(character.isalnum() for character in candidate):
        return False
    if _contains_cjk(candidate):
        return len(candidate) >= 2
    return len(candidate) >= 3 and any(
        _is_latin_letter(character) for character in candidate
    )


def _whole_occurrences(source: str, candidate: str) -> tuple[int, ...]:
    starts: list[int] = []
    offset = 0
    while (start := source.find(candidate, offset)) >= 0:
        end = start + len(candidate)
        before = source[start - 1] if start else ""
        after = source[end] if end < len(source) else ""
        if not (_word_character(before) or _word_character(after)):
            starts.append(start)
        offset = start + 1
    return tuple(starts)


def _is_unique_text(source: str, candidate: str) -> bool:
    return source.casefold().count(candidate.casefold()) == 1


def _word_character(value: str) -> bool:
    return bool(value) and (value.isalnum() or value == "_")


def _latin_candidates(source: str) -> tuple[str, ...]:
    words: list[str] = []
    start: int | None = None
    for index, character in enumerate(source):
        if _is_latin_letter(character):
            if start is None:
                start = index
        elif start is not None:
            words.append(source[start:index])
            start = None
    if start is not None:
        words.append(source[start:])
    return tuple(words)


def _cjk_candidates(source: str) -> tuple[str, ...]:
    candidates: list[str] = []
    run: list[str] = []
    for character in source:
        if _is_cjk(character):
            run.append(character)
            continue
        candidates.extend(_cjk_ngrams("".join(run)))
        run.clear()
    candidates.extend(_cjk_ngrams("".join(run)))
    return tuple(candidates)


def _has_repeated_cjk_run(source: str) -> bool:
    run: list[str] = []
    for character in source:
        if _is_cjk(character):
            run.append(character)
            continue
        if _is_exact_repeat("".join(run)):
            return True
        run.clear()
    return _is_exact_repeat("".join(run))


def _is_exact_repeat(value: str) -> bool:
    if len(value) < 4 or len(value) % 2:
        return False
    midpoint = len(value) // 2
    return value[:midpoint] == value[midpoint:]


def _cjk_ngrams(run: str) -> tuple[str, ...]:
    return tuple(
        run[start : start + length]
        for length in range(min(4, len(run)), 1, -1)
        for start in range(0, len(run) - length + 1)
    )


def _contains_cjk(value: str) -> bool:
    return any(_is_cjk(character) for character in value)


def _is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def _is_latin_letter(character: str) -> bool:
    return character.isalpha() and "LATIN" in unicodedata.name(character, "")


def _build_prompt(source: str, answer: str) -> str | None:
    start = source.find(answer)
    if start < 0 or not _is_unique_text(source, answer):
        return None
    blanked = source[:start] + BLANK + source[start + len(answer) :]
    prompt = f"Fill in the missing term using the source context:\n\n{blanked}"
    if len(prompt) > MAX_PROMPT_CHARS or answer.casefold() in prompt.casefold():
        return None
    return prompt
