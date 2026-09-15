from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .domain import IntentDNA
from .intent_dna import evaluate_gate, fingerprint
from .intent_quality import can_lock_intent, score_intent


class IntentLockDenied(ValueError):
    pass


@dataclass(frozen=True)
class HumanApproval:
    approved_by: UUID
    approver_role: str
    expected_fingerprint: str
    decision: str
    decided_at: datetime
    is_human: bool = True


@dataclass(frozen=True)
class IntentAuditEvent:
    event_id: UUID
    event_type: str
    actor_id: UUID
    previous_fingerprint: str | None
    resulting_fingerprint: str
    occurred_at: datetime


@dataclass(frozen=True)
class IntentLockResult:
    intent_dna: IntentDNA
    audit_event: IntentAuditEvent


def _validate_approval(approval: HumanApproval, current_fingerprint: str) -> None:
    if not approval.is_human:
        raise IntentLockDenied("HUMAN_APPROVAL_REQUIRED")
    if approval.decision != "APPROVE":
        raise IntentLockDenied("APPROVAL_DECISION_REQUIRED")
    if approval.expected_fingerprint != current_fingerprint:
        raise IntentLockDenied("STALE_OR_MISMATCHED_APPROVAL")


def lock_intent(dna: IntentDNA, approval: HumanApproval) -> IntentLockResult:
    current_fingerprint = fingerprint(dna)
    _validate_approval(approval, current_fingerprint)
    if dna.locked:
        raise IntentLockDenied("ALREADY_LOCKED")
    if not evaluate_gate(dna).ready or not can_lock_intent(score_intent(dna)):
        raise IntentLockDenied("INTENT_QUALITY_GATE_FAILED")
    locked = dna.model_copy(update={"fingerprint": current_fingerprint, "locked": True}, deep=True)
    event = IntentAuditEvent(
        event_id=uuid4(),
        event_type="INTENT_DNA_LOCKED",
        actor_id=approval.approved_by,
        previous_fingerprint=None,
        resulting_fingerprint=current_fingerprint,
        occurred_at=datetime.now(UTC),
    )
    return IntentLockResult(locked, event)


def approve_mutation(
    locked_dna: IntentDNA,
    replacement: IntentDNA,
    approval: HumanApproval,
) -> IntentLockResult:
    if not locked_dna.locked or not locked_dna.fingerprint:
        raise IntentLockDenied("LOCKED_INTENT_REQUIRED")
    _validate_approval(approval, locked_dna.fingerprint)
    replacement_fingerprint = fingerprint(replacement)
    if replacement_fingerprint == locked_dna.fingerprint:
        raise IntentLockDenied("NO_INTENT_CHANGE")
    if not evaluate_gate(replacement).ready or not can_lock_intent(score_intent(replacement)):
        raise IntentLockDenied("INTENT_QUALITY_GATE_FAILED")
    new_version = replacement.model_copy(
        update={"fingerprint": replacement_fingerprint, "locked": True}, deep=True
    )
    event = IntentAuditEvent(
        event_id=uuid4(),
        event_type="INTENT_DNA_MUTATION_APPROVED",
        actor_id=approval.approved_by,
        previous_fingerprint=locked_dna.fingerprint,
        resulting_fingerprint=replacement_fingerprint,
        occurred_at=datetime.now(UTC),
    )
    return IntentLockResult(new_version, event)
