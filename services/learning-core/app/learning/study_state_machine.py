"""Pure state transitions for a Deep Learn session.

Persistence and event logging belong to the caller.  Keeping the transition
rules here makes it impossible for an LLM-generated value to invent a state or
skip a required phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DeepLearnState(StrEnum):
    DRAFT = "draft"
    GOAL_CONFIRMATION = "goal_confirmation"
    DIAGNOSING = "diagnosing"
    PLANNING = "planning"
    STUDYING = "studying"
    CHECKPOINT = "checkpoint"
    ACTIVE_RECALL = "active_recall"
    PRACTICING = "practicing"
    SUMMARIZING = "summarizing"
    REVIEW_SCHEDULING = "review_scheduling"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


CANONICAL_FLOW: tuple[DeepLearnState, ...] = (
    DeepLearnState.DRAFT,
    DeepLearnState.GOAL_CONFIRMATION,
    DeepLearnState.DIAGNOSING,
    DeepLearnState.PLANNING,
    DeepLearnState.STUDYING,
    DeepLearnState.CHECKPOINT,
    DeepLearnState.ACTIVE_RECALL,
    DeepLearnState.PRACTICING,
    DeepLearnState.SUMMARIZING,
    DeepLearnState.REVIEW_SCHEDULING,
    DeepLearnState.COMPLETED,
)

TERMINAL_STATES = frozenset(
    {
        DeepLearnState.COMPLETED,
        DeepLearnState.CANCELLED,
        DeepLearnState.FAILED,
    }
)

_DIRECT_TRANSITIONS = {
    current: frozenset({following})
    for current, following in zip(CANONICAL_FLOW, CANONICAL_FLOW[1:])
}
_PAUSABLE_STATES = frozenset(CANONICAL_FLOW[:-1])


class InvalidStudyStateTransition(ValueError):
    """Raised when a requested transition violates the canonical flow."""


@dataclass(frozen=True, slots=True)
class StudyStateTransition:
    previous: DeepLearnState
    current: DeepLearnState
    resume_from_status: DeepLearnState | None = None

    @property
    def terminal(self) -> bool:
        return self.current in TERMINAL_STATES


def _state(value: DeepLearnState | str, *, field: str) -> DeepLearnState:
    try:
        return DeepLearnState(value)
    except ValueError as error:
        raise InvalidStudyStateTransition(f"unknown {field}: {value!r}") from error


def transition_study_state(
    current: DeepLearnState | str,
    target: DeepLearnState | str,
    *,
    resume_from_status: DeepLearnState | str | None = None,
) -> StudyStateTransition:
    """Validate and return one atomic session transition.

    Pausing records the exact active state in ``resume_from_status``.  Resuming
    is only legal back to that saved state, preventing a caller from using a
    pause as a shortcut through the canonical flow.
    """

    previous = _state(current, field="current state")
    following = _state(target, field="target state")
    saved = (
        _state(resume_from_status, field="resume state")
        if resume_from_status is not None
        else None
    )

    if previous in TERMINAL_STATES:
        raise InvalidStudyStateTransition(
            f"terminal state {previous.value!r} cannot transition"
        )

    if following in {DeepLearnState.CANCELLED, DeepLearnState.FAILED}:
        return StudyStateTransition(previous, following)

    if previous is DeepLearnState.PAUSED:
        if saved is None:
            raise InvalidStudyStateTransition("resuming requires resume_from_status")
        if saved not in _PAUSABLE_STATES:
            raise InvalidStudyStateTransition(
                f"invalid saved resume state: {saved.value!r}"
            )
        if following is not saved:
            raise InvalidStudyStateTransition(
                f"paused session may only resume to {saved.value!r}"
            )
        return StudyStateTransition(previous, following)

    if saved is not None:
        raise InvalidStudyStateTransition(
            "resume_from_status is only valid while current state is paused"
        )

    if following is DeepLearnState.PAUSED:
        if previous not in _PAUSABLE_STATES:
            raise InvalidStudyStateTransition(
                f"state {previous.value!r} cannot be paused"
            )
        return StudyStateTransition(previous, following, previous)

    allowed = _DIRECT_TRANSITIONS.get(previous, frozenset())
    if following not in allowed:
        raise InvalidStudyStateTransition(
            f"illegal Deep Learn transition: {previous.value!r} -> {following.value!r}"
        )
    return StudyStateTransition(previous, following)
