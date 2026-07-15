from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BktParameters:
    slip: float = 0.1
    guess: float = 0.2
    transit: float = 0.1

    def __post_init__(self) -> None:
        for name, value in (
            ("slip", self.slip),
            ("guess", self.guess),
            ("transit", self.transit),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


def update_bkt(
    prior: float,
    *,
    correct: bool,
    parameters: BktParameters = BktParameters(),
) -> float:
    """Return P(learned) after one observation and one learning transition."""

    if not 0.0 <= prior <= 1.0:
        raise ValueError("prior must be between 0 and 1")

    if correct:
        learned_likelihood = 1.0 - parameters.slip
        unlearned_likelihood = parameters.guess
    else:
        learned_likelihood = parameters.slip
        unlearned_likelihood = 1.0 - parameters.guess

    numerator = prior * learned_likelihood
    denominator = numerator + (1.0 - prior) * unlearned_likelihood
    posterior = prior if denominator == 0 else numerator / denominator
    transitioned = posterior + (1.0 - posterior) * parameters.transit
    return round(min(1.0, max(0.0, transitioned)), 6)
