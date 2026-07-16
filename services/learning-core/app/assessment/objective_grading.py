"""Deterministic grading for objective assessment items."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any


class ObjectiveItemType(StrEnum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"


@dataclass(frozen=True, slots=True)
class FillBlankNormalization:
    """Explicit answer matching policy for a fill-blank item."""

    case_sensitive: bool = False
    trim: bool = True
    collapse_whitespace: bool = True
    unicode_form: str = "NFKC"

    def __post_init__(self) -> None:
        if self.unicode_form not in {"NFC", "NFD", "NFKC", "NFKD"}:
            raise ValueError("unicode_form must be NFC, NFD, NFKC, or NFKD")


@dataclass(frozen=True, slots=True)
class ObjectiveGrade:
    """A result safe to expose after submission; it never contains the answer."""

    item_type: ObjectiveItemType
    correct: bool
    score: float
    max_score: float
    grader_version: str = "objective-grader/1.0.0"

    @property
    def correctness(self) -> float:
        return 1.0 if self.correct else 0.0


def _choice_id(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty option identifier")
    return value.strip()


def _choice_set(value: Any, *, field: str) -> frozenset[str]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise ValueError(f"{field} must be a collection of option identifiers")
    identifiers = [_choice_id(item, field=field) for item in value]
    if not identifiers:
        raise ValueError(f"{field} cannot be empty")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{field} cannot contain duplicate option identifiers")
    return frozenset(identifiers)


_TRUE_VALUES = frozenset({"true", "t", "1"})
_FALSE_VALUES = frozenset({"false", "f", "0"})


def _boolean(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    raise ValueError(f"{field} must be a boolean")


def normalize_fill_blank(value: Any, policy: FillBlankNormalization) -> str:
    if not isinstance(value, str):
        raise ValueError("fill-blank answers must be strings")
    normalized = unicodedata.normalize(policy.unicode_form, value)
    if policy.trim:
        normalized = normalized.strip()
    if policy.collapse_whitespace:
        normalized = re.sub(r"\s+", " ", normalized)
    if not policy.case_sensitive:
        normalized = normalized.casefold()
    return normalized


def grade_objective_answer(
    item_type: ObjectiveItemType | str,
    submitted_answer: Any,
    expected_answer: Any,
    *,
    max_score: float = 1.0,
    fill_blank_policy: FillBlankNormalization = FillBlankNormalization(),
) -> ObjectiveGrade:
    """Grade one submitted answer without returning expected-answer material."""

    try:
        kind = ObjectiveItemType(item_type)
    except ValueError as error:
        raise ValueError(f"unsupported objective item type: {item_type!r}") from error
    if not isinstance(max_score, (int, float)) or isinstance(max_score, bool):
        raise ValueError("max_score must be a positive number")
    if not isfinite(max_score) or max_score <= 0:
        raise ValueError("max_score must be positive")

    if kind is ObjectiveItemType.SINGLE_CHOICE:
        correct = _choice_id(submitted_answer, field="submitted answer") == _choice_id(
            expected_answer, field="expected answer"
        )
    elif kind is ObjectiveItemType.MULTIPLE_CHOICE:
        correct = _choice_set(
            submitted_answer, field="submitted answer"
        ) == _choice_set(expected_answer, field="expected answer")
    elif kind is ObjectiveItemType.TRUE_FALSE:
        correct = _boolean(submitted_answer, field="submitted answer") is _boolean(
            expected_answer, field="expected answer"
        )
    else:
        submitted = normalize_fill_blank(submitted_answer, fill_blank_policy)
        if isinstance(expected_answer, str):
            accepted_answers = (expected_answer,)
        elif isinstance(expected_answer, Iterable) and not isinstance(
            expected_answer, Mapping
        ):
            accepted_answers = tuple(expected_answer)
        else:
            raise ValueError(
                "expected answer must be a string or collection of strings"
            )
        if not accepted_answers:
            raise ValueError("expected answer cannot be empty")
        accepted = set()
        for answer in accepted_answers:
            normalized_answer = normalize_fill_blank(answer, fill_blank_policy)
            if not normalized_answer:
                raise ValueError("accepted fill-blank answers cannot be empty")
            accepted.add(normalized_answer)
        correct = submitted in accepted

    numeric_max = float(max_score)
    return ObjectiveGrade(
        item_type=kind,
        correct=correct,
        score=numeric_max if correct else 0.0,
        max_score=numeric_max,
    )
