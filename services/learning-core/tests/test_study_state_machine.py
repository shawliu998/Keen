from __future__ import annotations

import pytest

from app.learning.study_state_machine import (
    CANONICAL_FLOW,
    TERMINAL_STATES,
    DeepLearnState,
    InvalidStudyStateTransition,
    transition_study_state,
)


def test_canonical_deep_learn_flow_advances_one_phase_at_a_time():
    for current, target in zip(CANONICAL_FLOW, CANONICAL_FLOW[1:]):
        result = transition_study_state(current, target)
        assert result.previous is current
        assert result.current is target
        assert result.resume_from_status is None


def test_completed_unit_may_loop_from_practice_to_the_next_study_unit():
    result = transition_study_state("practicing", "studying")

    assert result.previous is DeepLearnState.PRACTICING
    assert result.current is DeepLearnState.STUDYING


def test_pause_persists_resume_state_and_resume_must_match_it():
    paused = transition_study_state("studying", "paused")

    assert paused.current is DeepLearnState.PAUSED
    assert paused.resume_from_status is DeepLearnState.STUDYING
    resumed = transition_study_state(
        paused.current, "studying", resume_from_status=paused.resume_from_status
    )
    assert resumed.current is DeepLearnState.STUDYING
    assert resumed.resume_from_status is None

    with pytest.raises(InvalidStudyStateTransition, match="may only resume"):
        transition_study_state("paused", "checkpoint", resume_from_status="studying")
    with pytest.raises(InvalidStudyStateTransition, match="requires"):
        transition_study_state("paused", "studying")


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES))
def test_terminal_states_cannot_transition(terminal):
    with pytest.raises(InvalidStudyStateTransition, match="terminal"):
        transition_study_state(terminal, "paused")


def test_active_state_can_cancel_or_fail_but_cannot_skip_phases():
    assert transition_study_state("planning", "cancelled").terminal is True
    assert transition_study_state("planning", "failed").terminal is True
    assert transition_study_state("paused", "cancelled").terminal is True

    with pytest.raises(InvalidStudyStateTransition, match="illegal"):
        transition_study_state("draft", "studying")
    with pytest.raises(InvalidStudyStateTransition, match="illegal"):
        transition_study_state("studying", "studying")
    with pytest.raises(InvalidStudyStateTransition, match="unknown target"):
        transition_study_state("draft", "invented")
