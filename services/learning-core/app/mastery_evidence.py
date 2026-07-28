"""Evidence-weighted deterministic mastery updates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from app.assessment.hints import DEFAULT_HINT_PARAMETERS, HintParameters, hint_impact
from app.mastery import BktParameters, update_bkt


class ResponseType(StrEnum):
    OBJECTIVE = "objective"
    SUBJECTIVE = "subjective"
    ACTIVE_RECALL = "active_recall"
    PRACTICE = "practice"
    DIAGNOSTIC = "diagnostic"
    REVIEW = "review"
    CONTENT_READ = "content_read"
    USER_REPORT = "user_report"


@dataclass(frozen=True, slots=True)
class MasteryEvidenceParameters:
    algorithm: str = "weighted_bkt"
    version: str = "weighted-bkt/1.0.0"
    difficulty_floor: float = 0.75
    confidence_floor: float = 0.75
    ambiguity_floor: float = 0.25
    response_type_factors: tuple[tuple[ResponseType, float], ...] = (
        (ResponseType.OBJECTIVE, 0.85),
        (ResponseType.SUBJECTIVE, 0.80),
        (ResponseType.ACTIVE_RECALL, 0.90),
        (ResponseType.PRACTICE, 0.85),
        (ResponseType.DIAGNOSTIC, 0.50),
        (ResponseType.REVIEW, 0.85),
        (ResponseType.CONTENT_READ, 0.05),
        (ResponseType.USER_REPORT, 0.00),
    )

    def __post_init__(self) -> None:
        for name, value in (
            ("algorithm", self.algorithm),
            ("version", self.version),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise ValueError(f"{name} must be a non-empty trimmed string")
        for name, value in (
            ("difficulty_floor", self.difficulty_floor),
            ("confidence_floor", self.confidence_floor),
            ("ambiguity_floor", self.ambiguity_floor),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{name} must be between 0 and 1")
        factors = dict(self.response_type_factors)
        if set(factors) != set(ResponseType):
            raise ValueError("response_type_factors must define every response type")
        if len(factors) != len(self.response_type_factors):
            raise ValueError("response_type_factors cannot contain duplicates")
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            or not 0.0 <= value <= 1.0
            for value in factors.values()
        ):
            raise ValueError("response type factors must be between 0 and 1")
        if factors[ResponseType.USER_REPORT] != 0.0:
            raise ValueError("user_report evidence weight must remain zero")

    def response_factor(self, response_type: ResponseType) -> float:
        return dict(self.response_type_factors)[response_type]


DEFAULT_MASTERY_EVIDENCE_PARAMETERS = MasteryEvidenceParameters()


@dataclass(frozen=True, slots=True)
class MasteryEvidence:
    correctness: float
    independence: float
    hint_level: int
    difficulty: float
    confidence: float
    response_type: ResponseType

    def __post_init__(self) -> None:
        for name, value in (
            ("correctness", self.correctness),
            ("independence", self.independence),
            ("difficulty", self.difficulty),
            ("confidence", self.confidence),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
            ):
                raise ValueError(f"{name} must be numeric")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        try:
            response_type = ResponseType(self.response_type)
        except ValueError as error:
            raise ValueError(
                f"unknown response type: {self.response_type!r}"
            ) from error
        object.__setattr__(self, "response_type", response_type)
        hint_impact(self.hint_level)


@dataclass(frozen=True, slots=True)
class WeightedMasteryUpdate:
    before: float
    after: float
    unweighted_target: float
    evidence_weight: float
    algorithm: str
    algorithm_version: str


def calculate_evidence_weight(
    evidence: MasteryEvidence,
    *,
    parameters: MasteryEvidenceParameters = DEFAULT_MASTERY_EVIDENCE_PARAMETERS,
    hint_parameters: HintParameters = DEFAULT_HINT_PARAMETERS,
) -> float:
    """Return a reproducible evidence weight constrained to ``[0, 1]``."""

    response_factor = parameters.response_factor(evidence.response_type)
    if response_factor == 0.0:
        return 0.0
    assistance = hint_impact(evidence.hint_level, hint_parameters)
    independence = min(evidence.independence, assistance.independence)
    difficulty_factor = parameters.difficulty_floor + (
        (1.0 - parameters.difficulty_floor) * evidence.difficulty
    )
    confidence_factor = parameters.confidence_floor + (
        (1.0 - parameters.confidence_floor) * evidence.confidence
    )
    decisiveness = parameters.ambiguity_floor + (
        (1.0 - parameters.ambiguity_floor) * abs((2.0 * evidence.correctness) - 1.0)
    )
    weight = (
        response_factor
        * independence
        * assistance.evidence_factor
        * difficulty_factor
        * confidence_factor
        * decisiveness
    )
    return round(min(1.0, max(0.0, weight)), 6)


def update_mastery_from_evidence(
    prior: float,
    evidence: MasteryEvidence,
    *,
    parameters: MasteryEvidenceParameters = DEFAULT_MASTERY_EVIDENCE_PARAMETERS,
    bkt_parameters: BktParameters = BktParameters(),
    hint_parameters: HintParameters = DEFAULT_HINT_PARAMETERS,
) -> WeightedMasteryUpdate:
    """Blend existing BKT outcomes using correctness and evidence strength."""

    if not 0.0 <= prior <= 1.0:
        raise ValueError("prior must be between 0 and 1")
    weight = calculate_evidence_weight(
        evidence, parameters=parameters, hint_parameters=hint_parameters
    )
    correct_target = update_bkt(prior, correct=True, parameters=bkt_parameters)
    incorrect_target = update_bkt(prior, correct=False, parameters=bkt_parameters)
    target = (
        evidence.correctness * correct_target
        + (1.0 - evidence.correctness) * incorrect_target
    )
    after = prior + weight * (target - prior)
    return WeightedMasteryUpdate(
        before=round(min(1.0, max(0.0, prior)), 6),
        after=round(min(1.0, max(0.0, after)), 6),
        unweighted_target=round(min(1.0, max(0.0, target)), 6),
        evidence_weight=weight,
        algorithm=parameters.algorithm,
        algorithm_version=parameters.version,
    )
