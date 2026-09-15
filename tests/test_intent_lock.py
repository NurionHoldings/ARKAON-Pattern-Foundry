from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apf.domain import INTENT_AXES, IntentDNA, IntentStatement
from apf.intent_dna import fingerprint
from apf.intent_lock import (
    HumanApproval,
    IntentLockDenied,
    approve_mutation,
    lock_intent,
)


def statement(text: str) -> IntentStatement:
    return IntentStatement(
        canonical_text=text,
        evidence_refs=[uuid4()],
        confidence=1,
        stability="CORE",
    )


def complete_dna(suffix: str = "v1") -> IntentDNA:
    return IntentDNA(
        analysis_run_id=uuid4(),
        axes={axis: [statement(f"{axis} intent {suffix}")] for axis in INTENT_AXES},
        completeness=1,
    )


def approval(expected: str, **changes) -> HumanApproval:
    values = {
        "approved_by": uuid4(),
        "approver_role": "OWNER",
        "expected_fingerprint": expected,
        "decision": "APPROVE",
        "decided_at": datetime.now(UTC),
    }
    values.update(changes)
    return HumanApproval(**values)


def test_human_can_lock_quality_passed_intent():
    dna = complete_dna()
    result = lock_intent(dna, approval(fingerprint(dna)))
    assert result.intent_dna.locked
    assert result.audit_event.event_type == "INTENT_DNA_LOCKED"
    assert not dna.locked


def test_ai_cannot_self_lock_intent():
    dna = complete_dna()
    with pytest.raises(IntentLockDenied, match="HUMAN_APPROVAL_REQUIRED"):
        lock_intent(dna, approval(fingerprint(dna), is_human=False))


def test_stale_approval_cannot_lock_changed_intent():
    dna = complete_dna()
    with pytest.raises(IntentLockDenied, match="STALE_OR_MISMATCHED_APPROVAL"):
        lock_intent(dna, approval("0" * 64))


def test_locked_intent_mutation_creates_new_approved_version_and_audit_event():
    original = complete_dna()
    locked = lock_intent(original, approval(fingerprint(original))).intent_dna
    replacement = complete_dna("v2")
    result = approve_mutation(
        locked,
        replacement,
        approval(
            locked.fingerprint,
            expected_resulting_fingerprint=fingerprint(replacement),
        ),
    )
    assert result.intent_dna.locked
    assert result.intent_dna.fingerprint != locked.fingerprint
    assert result.audit_event.previous_fingerprint == locked.fingerprint
    assert result.audit_event.event_type == "INTENT_DNA_MUTATION_APPROVED"


def test_approval_for_different_replacement_cannot_authorize_mutation():
    original = complete_dna()
    locked = lock_intent(original, approval(fingerprint(original))).intent_dna
    approved_replacement = complete_dna("approved")
    substituted_replacement = complete_dna("substituted")
    with pytest.raises(IntentLockDenied, match="UNAPPROVED_MUTATION_RESULT"):
        approve_mutation(
            locked,
            substituted_replacement,
            approval(
                locked.fingerprint,
                expected_resulting_fingerprint=fingerprint(approved_replacement),
            ),
        )


def test_unlocked_intent_cannot_enter_mutation_path():
    original = complete_dna()
    with pytest.raises(IntentLockDenied, match="LOCKED_INTENT_REQUIRED"):
        approve_mutation(original, complete_dna("v2"), approval(fingerprint(original)))
