"""Versioned hint penalties and evidence factors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from math import isfinite


class HintLevel(IntEnum):
    NONE = 0
    DIRECTION = 1
    KEY_CONCEPT = 2
    PARTIAL_STEPS = 3
    NEAR_COMPLETE_SOLUTION = 4


@dataclass(frozen=True, slots=True)
class HintParameters:
    version: str = "hint-penalties/1.0.0"
    penalties: tuple[float, ...] = (0.0, 0.15, 0.30, 0.45, 0.60)
    independence: tuple[float, ...] = (1.0, 0.80, 0.60, 0.40, 0.20)
    evidence_factors: tuple[float, ...] = (1.0, 0.75, 0.55, 0.35, 0.20)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.version, str)
            or not self.version.strip()
            or self.version != self.version.strip()
        ):
            raise ValueError("version must be a non-empty trimmed string")
        expected_length = len(HintLevel)
        for name, values in (
            ("penalties", self.penalties),
            ("independence", self.independence),
            ("evidence_factors", self.evidence_factors),
        ):
            if len(values) != expected_length:
                raise ValueError(f"{name} must define every hint level")
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                or not 0.0 <= value <= 1.0
                for value in values
            ):
                raise ValueError(f"{name} values must be between 0 and 1")
        if any(left > right for left, right in zip(self.penalties, self.penalties[1:])):
            raise ValueError("hint penalties must be monotonically non-decreasing")
        for name, values in (
            ("independence", self.independence),
            ("evidence_factors", self.evidence_factors),
        ):
            if any(left < right for left, right in zip(values, values[1:])):
                raise ValueError(f"{name} must be monotonically non-increasing")


DEFAULT_HINT_PARAMETERS = HintParameters()


@dataclass(frozen=True, slots=True)
class HintImpact:
    level: HintLevel
    penalty: float
    independence: float
    evidence_factor: float
    version: str


def hint_impact(
    level: HintLevel | int,
    parameters: HintParameters = DEFAULT_HINT_PARAMETERS,
) -> HintImpact:
    if isinstance(level, bool):
        raise ValueError("hint level must be between 0 and 4")
    try:
        normalized_level = HintLevel(level)
    except ValueError as error:
        raise ValueError("hint level must be between 0 and 4") from error
    index = int(normalized_level)
    return HintImpact(
        level=normalized_level,
        penalty=parameters.penalties[index],
        independence=parameters.independence[index],
        evidence_factor=parameters.evidence_factors[index],
        version=parameters.version,
    )
