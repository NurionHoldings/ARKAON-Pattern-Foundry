import pytest

from apf.domain import CandidateState, RunState, TargetState
from apf.state_machine import (
    CANDIDATE_TRANSITIONS,
    RUN_TRANSITIONS,
    TARGET_TRANSITIONS,
    InvalidTransition,
    transition,
)


def test_valid_transitions():
    assert transition(TargetState.DRAFT, TargetState.AUTHORIZATION_PENDING, TARGET_TRANSITIONS) == TargetState.AUTHORIZATION_PENDING
    assert transition(RunState.QUEUED, RunState.INTENT_SCOPING, RUN_TRANSITIONS) == RunState.INTENT_SCOPING
    assert transition(CandidateState.APPROVED, CandidateState.PUBLISHED, CANDIDATE_TRANSITIONS) == CandidateState.PUBLISHED


def test_state_skipping_is_forbidden():
    with pytest.raises(InvalidTransition):
        transition(CandidateState.DRAFT, CandidateState.PUBLISHED, CANDIDATE_TRANSITIONS)

