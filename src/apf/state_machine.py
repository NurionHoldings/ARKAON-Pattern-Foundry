from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from .domain import CandidateState, RunState, TargetState


class InvalidTransition(ValueError):
    pass


TARGET_TRANSITIONS: Mapping[TargetState, frozenset[TargetState]] = {
    TargetState.DRAFT: frozenset({TargetState.AUTHORIZATION_PENDING, TargetState.ARCHIVED}),
    TargetState.AUTHORIZATION_PENDING: frozenset({TargetState.AUTHORIZED, TargetState.SUSPENDED}),
    TargetState.AUTHORIZED: frozenset({TargetState.INGESTING, TargetState.SUSPENDED}),
    TargetState.INGESTING: frozenset({TargetState.READY, TargetState.SUSPENDED}),
    TargetState.READY: frozenset({TargetState.SUSPENDED, TargetState.ARCHIVED}),
    TargetState.SUSPENDED: frozenset({TargetState.AUTHORIZATION_PENDING, TargetState.ARCHIVED}),
    TargetState.ARCHIVED: frozenset(),
}

RUN_TRANSITIONS: Mapping[RunState, frozenset[RunState]] = {
    RunState.QUEUED: frozenset({RunState.INTENT_SCOPING, RunState.HOLD, RunState.CANCELLED}),
    RunState.INTENT_SCOPING: frozenset({RunState.ANALYZING, RunState.HOLD, RunState.FAILED}),
    RunState.ANALYZING: frozenset({RunState.ABSTRACTING, RunState.PARTIAL_REVIEW, RunState.HOLD, RunState.FAILED}),
    RunState.ABSTRACTING: frozenset({RunState.VALIDATING, RunState.HOLD, RunState.FAILED}),
    RunState.VALIDATING: frozenset({RunState.REVIEW_PENDING, RunState.QUARANTINED, RunState.HOLD, RunState.FAILED}),
    RunState.REVIEW_PENDING: frozenset({RunState.COMPLETED, RunState.HOLD}),
    RunState.PARTIAL_REVIEW: frozenset({RunState.ANALYZING, RunState.HOLD, RunState.CANCELLED}),
    RunState.HOLD: frozenset({RunState.INTENT_SCOPING, RunState.CANCELLED}),
    RunState.FAILED: frozenset(), RunState.CANCELLED: frozenset(),
    RunState.QUARANTINED: frozenset(), RunState.COMPLETED: frozenset(),
}

CANDIDATE_TRANSITIONS: Mapping[CandidateState, frozenset[CandidateState]] = {
    CandidateState.DRAFT: frozenset({CandidateState.EVIDENCE_CHECKED, CandidateState.REJECTED}),
    CandidateState.EVIDENCE_CHECKED: frozenset({CandidateState.VALIDATED, CandidateState.REJECTED}),
    CandidateState.VALIDATED: frozenset({CandidateState.REVIEW_PENDING, CandidateState.REJECTED}),
    CandidateState.REVIEW_PENDING: frozenset({CandidateState.APPROVED, CandidateState.CHANGES_REQUESTED, CandidateState.REJECTED}),
    CandidateState.CHANGES_REQUESTED: frozenset({CandidateState.DRAFT, CandidateState.REJECTED}),
    CandidateState.APPROVED: frozenset({CandidateState.PUBLISHED}),
    CandidateState.PUBLISHED: frozenset({CandidateState.DEPRECATED, CandidateState.REVOKED, CandidateState.SUPERSEDED}),
    CandidateState.DEPRECATED: frozenset({CandidateState.REVOKED, CandidateState.SUPERSEDED}),
    CandidateState.REJECTED: frozenset(), CandidateState.REVOKED: frozenset(), CandidateState.SUPERSEDED: frozenset(),
}


def transition(current: Enum, desired: Enum, graph: Mapping[Enum, frozenset[Enum]]) -> Enum:
    if desired not in graph.get(current, frozenset()):
        raise InvalidTransition(f"{current.value} -> {desired.value} is forbidden")
    return desired

