import json

import pytest

from apf.arkaon_audit_bot import AuditBotError
from apf.audit_bot_learning import (
    FeedbackKind,
    LearningFeedback,
    LearningPolicy,
    ReviewerRole,
    append_feedback,
    load_feedback,
    propose_upgrade,
)


def feedback(identifier, reviewer, role, kind=FeedbackKind.MISSED_FINDING):
    digit = str(int(identifier.split("-")[-1]) % 10)
    return LearningFeedback(
        feedback_id=identifier,
        source_manifest_digest="sha256:" + "a" * 64,
        finding_code="NEW_UNSAFE_PATTERN",
        kind=kind,
        detail="confirmed by independent review",
        reviewer=reviewer,
        reviewer_role=role,
        review_receipt_digest="sha256:" + digit * 64,
        reviewed_at="2026-09-19T10:00:00+09:00",
    )


def registry(path, feedbacks):
    entries = []
    for item in feedbacks:
        entries.append(
            {
                "receipt_digest": item.review_receipt_digest,
                "reviewer": item.reviewer,
                "reviewer_role": item.reviewer_role.value,
                "source_manifest_digest": item.source_manifest_digest,
                "finding_code": item.finding_code,
                "feedback_kind": item.kind.value,
                "evidence_digest": "sha256:" + "e" * 64,
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": "apf.audit-review-receipt-registry/1.0",
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )


def append(ledger, receipt_registry, item, policy=None):
    return append_feedback(
        ledger,
        item,
        receipt_registry_path=receipt_registry,
        policy=policy or LearningPolicy(),
    )


def test_learning_ledger_is_hash_chained_and_tamper_evident(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    receipt_registry = tmp_path / "receipts.json"
    first_feedback = feedback("f-1", "arkaon", ReviewerRole.ARKAON)
    second_feedback = feedback("f-2", "eternian", ReviewerRole.ETERNIAN)
    registry(receipt_registry, [first_feedback, second_feedback])
    first = append(ledger, receipt_registry, first_feedback)
    second = append(ledger, receipt_registry, second_feedback)
    assert second.previous_digest == first.record_digest

    lines = ledger.read_text(encoding="utf-8").splitlines()
    changed = json.loads(lines[0])
    changed["feedback"]["detail"] = "tampered"
    lines[0] = json.dumps(changed)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(AuditBotError, match="AUDIT_LEARNING_LEDGER_TAMPERED"):
        load_feedback(ledger)


def test_two_receipt_bound_roles_create_propose_only_upgrade(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    receipt_registry = tmp_path / "receipts.json"
    items = [
        feedback("f-1", "arkaon", ReviewerRole.ARKAON),
        feedback("f-2", "eternian", ReviewerRole.ETERNIAN),
    ]
    registry(receipt_registry, items)
    for item in items:
        append(ledger, receipt_registry, item)

    proposal = propose_upgrade(load_feedback(ledger), request_id="audit-upgrade-001")

    assert proposal is not None
    assert proposal["state"] == "PROPOSED_ONLY"
    assert proposal["automatic_policy_mutation"] is False
    assert proposal["automatic_merge"] is False


def test_receipt_binding_duplicate_and_concurrent_writer_are_denied(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    receipt_registry = tmp_path / "receipts.json"
    item = feedback("f-1", "arkaon", ReviewerRole.ARKAON)
    registry(receipt_registry, [item])
    append(ledger, receipt_registry, item)
    with pytest.raises(AuditBotError, match="AUDIT_LEARNING_FEEDBACK_DUPLICATE"):
        append(ledger, receipt_registry, item)

    ledger.with_suffix(".jsonl.lock").write_text("busy", encoding="utf-8")
    other = feedback("f-2", "eternian", ReviewerRole.ETERNIAN)
    registry(receipt_registry, [item, other])
    with pytest.raises(AuditBotError, match="AUDIT_LEARNING_LEDGER_BUSY"):
        append(ledger, receipt_registry, other)


def test_bounded_segments_preserve_chain_then_apply_backpressure(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    receipt_registry = tmp_path / "receipts.json"
    items = [
        feedback(f"f-{index}", "arkaon" if index % 2 else "eternian", ReviewerRole.ARKAON if index % 2 else ReviewerRole.ETERNIAN)
        for index in range(1, 6)
    ]
    registry(receipt_registry, items)
    policy = LearningPolicy(max_records_per_segment=2, max_segments=1)
    for item in items[:4]:
        append(ledger, receipt_registry, item, policy)
    assert [record.sequence for record in load_feedback(ledger, policy=policy)] == [1, 2, 3, 4]
    with pytest.raises(AuditBotError, match="AUDIT_LEARNING_BACKPRESSURE"):
        append(ledger, receipt_registry, items[4], policy)


def test_nonhex_digest_and_receipt_identity_mismatch_are_denied(tmp_path):
    ledger = tmp_path / "audit-learning.jsonl"
    receipt_registry = tmp_path / "receipts.json"
    item = feedback("f-1", "arkaon", ReviewerRole.ARKAON)
    registry(receipt_registry, [item])
    forged = LearningFeedback(**{**item.__dict__, "reviewer": "attacker"})
    with pytest.raises(AuditBotError, match="AUDIT_REVIEW_RECEIPT_BINDING_MISMATCH"):
        append(ledger, receipt_registry, forged)
    invalid = LearningFeedback(**{**item.__dict__, "source_manifest_digest": "sha256:" + "z" * 64})
    with pytest.raises(AuditBotError, match="AUDIT_LEARNING_SOURCE_DIGEST_INVALID"):
        append(ledger, receipt_registry, invalid)
