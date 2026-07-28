"""Deterministic misconception inference from structured error evidence.

The rules in this module deliberately treat generated labels as presentation
metadata, not proof.  Persistence and any user-facing mutation belong to the
caller; this module only groups evidence and proposes a status.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class MisconceptionLabelSource(StrEnum):
    MODEL = "model"
    RULE = "rule"
    USER = "user"


class MisconceptionStatusSuggestion(StrEnum):
    CANDIDATE = "candidate"
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"


def _required_text(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field=field)


def _unit_interval(value: float, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{field} must be finite and between 0 and 1")
    return numeric


@dataclass(frozen=True, slots=True)
class MisconceptionEvidence:
    """One observed error, already separated from any generated prose."""

    evidence_id: str
    concept_id: str
    attempt_id: str
    item_id: str
    error_key: str | None = None
    selected_distractor_id: str | None = None
    failed_step_id: str | None = None
    response_confidence: float = 0.0
    candidate_label: str | None = None
    label_source: MisconceptionLabelSource | None = None
    user_confirmed: bool = False

    def __post_init__(self) -> None:
        for field in ("evidence_id", "concept_id", "attempt_id", "item_id"):
            object.__setattr__(
                self, field, _required_text(getattr(self, field), field=field)
            )
        for field in ("error_key", "selected_distractor_id", "failed_step_id"):
            object.__setattr__(
                self, field, _optional_text(getattr(self, field), field=field)
            )
        object.__setattr__(
            self,
            "response_confidence",
            _unit_interval(self.response_confidence, field="response_confidence"),
        )
        label = _optional_text(self.candidate_label, field="candidate_label")
        object.__setattr__(self, "candidate_label", label)
        if (label is None) is not (self.label_source is None):
            raise ValueError(
                "candidate_label and label_source must either both be set or both be absent"
            )
        if self.label_source is not None:
            try:
                object.__setattr__(
                    self,
                    "label_source",
                    MisconceptionLabelSource(self.label_source),
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"unsupported label source: {self.label_source!r}"
                ) from error
        if not isinstance(self.user_confirmed, bool):
            raise ValueError("user_confirmed must be a boolean")


@dataclass(frozen=True, slots=True)
class MisconceptionRuleParameters:
    version: str = "misconception-rules/1.0.0"
    high_confidence_threshold: float = 0.8
    suspected_attempt_threshold: int = 2
    confirmed_attempt_threshold: int = 3
    automatic_confidence_cap: float = 0.95

    def __post_init__(self) -> None:
        _required_text(self.version, field="version")
        _unit_interval(
            self.high_confidence_threshold, field="high_confidence_threshold"
        )
        _unit_interval(self.automatic_confidence_cap, field="automatic_confidence_cap")
        if (
            not isinstance(self.suspected_attempt_threshold, int)
            or isinstance(self.suspected_attempt_threshold, bool)
            or self.suspected_attempt_threshold < 2
        ):
            raise ValueError("suspected_attempt_threshold must be at least 2")
        if (
            not isinstance(self.confirmed_attempt_threshold, int)
            or isinstance(self.confirmed_attempt_threshold, bool)
            or self.confirmed_attempt_threshold <= self.suspected_attempt_threshold
        ):
            raise ValueError(
                "confirmed_attempt_threshold must exceed suspected_attempt_threshold"
            )


DEFAULT_MISCONCEPTION_RULES = MisconceptionRuleParameters()


@dataclass(frozen=True, slots=True)
class MisconceptionCandidate:
    candidate_id: str
    concept_id: str
    label: str | None
    label_source: MisconceptionLabelSource | None
    suggested_status: MisconceptionStatusSuggestion
    confidence: float
    evidence_ids: tuple[str, ...]
    distinct_attempt_count: int
    repeated_error: bool
    repeated_distractor: bool
    repeated_failed_step: bool
    high_confidence_error_count: int
    user_confirmed: bool
    reasons: tuple[str, ...]
    rule_version: str


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parents = list(range(size))

    def find(self, item: int) -> int:
        while self.parents[item] != item:
            self.parents[item] = self.parents[self.parents[item]]
            item = self.parents[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parents[right_root] = left_root


def _structural_keys(evidence: MisconceptionEvidence) -> tuple[str, ...]:
    """Return evidence keys allowed to corroborate an error.

    Candidate labels are intentionally absent: repeated model wording is not
    independent evidence that a misconception exists.
    """

    keys: list[str] = []
    if evidence.error_key is not None:
        keys.append(f"error:{evidence.error_key}")
    if evidence.selected_distractor_id is not None:
        keys.append(f"distractor:{evidence.selected_distractor_id}")
    if evidence.failed_step_id is not None:
        keys.append(f"step:{evidence.failed_step_id}")
    return tuple(keys)


def _repeated_across_attempts(
    evidence: list[MisconceptionEvidence], field: str
) -> bool:
    attempts_by_value: dict[str, set[str]] = defaultdict(set)
    for item in evidence:
        value = getattr(item, field)
        if value is not None:
            attempts_by_value[value].add(item.attempt_id)
    return any(len(attempts) >= 2 for attempts in attempts_by_value.values())


def _preferred_label(
    evidence: list[MisconceptionEvidence],
) -> tuple[str | None, MisconceptionLabelSource | None]:
    for source in (
        MisconceptionLabelSource.USER,
        MisconceptionLabelSource.RULE,
        MisconceptionLabelSource.MODEL,
    ):
        labels = [
            item.candidate_label
            for item in evidence
            if item.label_source is source and item.candidate_label is not None
        ]
        if labels:
            counts = Counter(labels)
            return min(counts, key=lambda label: (-counts[label], label)), source
    return None, None


def _candidate_id(concept_id: str, evidence_ids: tuple[str, ...]) -> str:
    fingerprint = "\x1f".join((concept_id, *evidence_ids)).encode()
    return f"misconception-{hashlib.sha256(fingerprint).hexdigest()[:20]}"


def infer_misconceptions(
    evidence: Iterable[MisconceptionEvidence],
    *,
    parameters: MisconceptionRuleParameters = DEFAULT_MISCONCEPTION_RULES,
) -> tuple[MisconceptionCandidate, ...]:
    """Group error evidence and return deterministic, non-mutating proposals."""

    items = sorted(evidence, key=lambda item: item.evidence_id)
    evidence_ids = [item.evidence_id for item in items]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("evidence_id values must be unique")
    if not items:
        return ()

    groups = _DisjointSet(len(items))
    key_owners: dict[tuple[str, str], int] = {}
    for index, item in enumerate(items):
        for key in _structural_keys(item):
            scoped_key = (item.concept_id, key)
            owner = key_owners.setdefault(scoped_key, index)
            groups.union(owner, index)

    grouped: dict[int, list[MisconceptionEvidence]] = defaultdict(list)
    for index, item in enumerate(items):
        grouped[groups.find(index)].append(item)

    candidates: list[MisconceptionCandidate] = []
    for group in grouped.values():
        group.sort(key=lambda item: item.evidence_id)
        concept_id = group[0].concept_id
        attempts = {item.attempt_id for item in group}
        repeated_error = _repeated_across_attempts(group, "error_key")
        repeated_distractor = _repeated_across_attempts(group, "selected_distractor_id")
        repeated_step = _repeated_across_attempts(group, "failed_step_id")
        high_confidence_count = len(
            {
                item.attempt_id
                for item in group
                if item.response_confidence >= parameters.high_confidence_threshold
            }
        )
        confirmed_by_user = any(item.user_confirmed for item in group)
        structural_pattern = repeated_error or repeated_distractor or repeated_step

        reasons = [f"observed in {len(attempts)} distinct attempt(s)"]
        if repeated_error:
            reasons.append("the same structured error recurred")
        if repeated_distractor:
            reasons.append("the same distractor was selected across attempts")
        if repeated_step:
            reasons.append("the same solution step failed across attempts")
        if high_confidence_count:
            reasons.append(
                f"{high_confidence_count} error(s) met the high-confidence threshold"
            )
        if confirmed_by_user:
            reasons.append("the learner explicitly confirmed the misconception")

        if confirmed_by_user:
            status = MisconceptionStatusSuggestion.CONFIRMED
        elif (
            len(attempts) >= parameters.confirmed_attempt_threshold
            and structural_pattern
        ):
            status = MisconceptionStatusSuggestion.CONFIRMED
        elif (
            len(attempts) >= parameters.suspected_attempt_threshold
            and structural_pattern
        ):
            status = MisconceptionStatusSuggestion.SUSPECTED
        else:
            # In particular, one observation can never auto-confirm, and
            # generated labels without corroborating structure stay candidates.
            status = MisconceptionStatusSuggestion.CANDIDATE

        if confirmed_by_user:
            confidence = 1.0
        else:
            confidence = 0.20
            confidence += min(0.40, max(0, len(attempts) - 1) * 0.20)
            confidence += 0.18 if repeated_error else 0.0
            confidence += 0.14 if repeated_distractor else 0.0
            confidence += 0.14 if repeated_step else 0.0
            confidence += min(0.16, high_confidence_count * 0.08)
            confidence = min(parameters.automatic_confidence_cap, confidence)

        ids = tuple(item.evidence_id for item in group)
        label, label_source = _preferred_label(group)
        candidates.append(
            MisconceptionCandidate(
                candidate_id=_candidate_id(concept_id, ids),
                concept_id=concept_id,
                label=label,
                label_source=label_source,
                suggested_status=status,
                confidence=round(confidence, 6),
                evidence_ids=ids,
                distinct_attempt_count=len(attempts),
                repeated_error=repeated_error,
                repeated_distractor=repeated_distractor,
                repeated_failed_step=repeated_step,
                high_confidence_error_count=high_confidence_count,
                user_confirmed=confirmed_by_user,
                reasons=tuple(reasons),
                rule_version=parameters.version,
            )
        )

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.confidence,
                candidate.concept_id,
                candidate.candidate_id,
            ),
        )
    )
