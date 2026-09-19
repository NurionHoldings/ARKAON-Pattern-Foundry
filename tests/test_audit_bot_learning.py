import json

import pytest

from apf.arkaon_audit_bot import AuditBotError
from apf.audit_bot_learning import (
    FeedbackKind,
    LearningFeedback,
    ReviewerRole,
    append_feedback,
    load_feedback,
    propose_upgrade,
)


def feedback(identifier, reviewer, role, kind=FeedbackKind.MISSED_FINDING):
    return LearningFeedback(
        feedback_id=identifier,
        source_manifest_digest="sha256:" + "a" * 64,
        finding_code="NEW_UNSAFE_PATTERN",
        kind=kind,
        detail="confirmed by independent review",
        reviewer=reviewer,
        reviewer_role=role,
        review_receipt_digest="sha256:" + "b" * 64,
        reviewed_at="2026-09-19T10:00:00+09:00",
    )


def test_learning_ledger_is_hash_chained_and_tamper_evident(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    first = append_feedback(ledger, feedback("f-1", "arkaon", ReviewerRole.ARKAON))
    second = append_feedback(ledger, feedback("f-2", "eternian", ReviewerRole.ETERNIAN))
    assert second.previous_digest == first.record_digest

    lines = ledger.read_text(encoding="utf-8").splitlines()
    changed = json.loads(lines[0])
    changed["feedback"]["detail"] = "tampered"
    lines[0] = json.dumps(changed)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(AuditBotError, match="AUDIT_LEARNING_LEDGER_TAMPERED"):
        load_feedback(ledger)


def test_two_independent_reviews_create_propose_only_upgrade(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    append_feedback(ledger, feedback("f-1", "arkaon", ReviewerRole.ARKAON))
    append_feedback(ledger, feedback("f-2", "eternian", ReviewerRole.ETERNIAN))

    proposal = propose_upgrade(load_feedback(ledger), request_id="audit-upgrade-001")

    assert proposal is not None
    assert proposal["state"] == "PROPOSED_ONLY"
    assert proposal["automatic_policy_mutation"] is False
    assert proposal["automatic_merge"] is False
    assert proposal["required_flow"][0] == "OWNER_APPROVED"


def test_one_reviewer_cannot_self_train_or_lower_safety_threshold(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    append_feedback(ledger, feedback("f-1", "arkaon", ReviewerRole.ARKAON))
    append_feedback(ledger, feedback("f-2", "arkaon", ReviewerRole.ARKAON))
    assert propose_upgrade(load_feedback(ledger), request_id="audit-upgrade-001") is None
    with pytest.raises(AuditBotError, match="LEARNING_THRESHOLD_UNSAFE"):
        propose_upgrade(load_feedback(ledger), request_id="audit-upgrade-001", minimum_confirmations=1)
