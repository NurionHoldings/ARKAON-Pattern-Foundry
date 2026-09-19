"""Append-only learning observations and propose-only upgrades for ARKAON Audit Bot."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from apf.arkaon_audit_bot import AuditBotError


class FeedbackKind(StrEnum):
    CONFIRMED_FINDING = "CONFIRMED_FINDING"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    MISSED_FINDING = "MISSED_FINDING"


class ReviewerRole(StrEnum):
    ARKAON = "ARKAON"
    ETERNIAN = "ETERNIAN"


@dataclass(frozen=True)
class LearningFeedback:
    feedback_id: str
    source_manifest_digest: str
    finding_code: str
    kind: FeedbackKind
    detail: str
    reviewer: str
    reviewer_role: ReviewerRole
    review_receipt_digest: str
    reviewed_at: str


@dataclass(frozen=True)
class LearningRecord:
    sequence: int
    previous_digest: str | None
    feedback: LearningFeedback
    record_digest: str


def append_feedback(ledger_path: Path, feedback: LearningFeedback) -> LearningRecord:
    _validate_feedback(feedback)
    records = load_feedback(ledger_path)
    sequence = len(records) + 1
    previous_digest = records[-1].record_digest if records else None
    unsigned = {
        "sequence": sequence,
        "previous_digest": previous_digest,
        "feedback": _feedback_document(feedback),
    }
    record = LearningRecord(
        sequence=sequence,
        previous_digest=previous_digest,
        feedback=feedback,
        record_digest=_digest(unsigned),
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(_record_document(record), sort_keys=True) + "\n")
    return record


def load_feedback(ledger_path: Path) -> tuple[LearningRecord, ...]:
    if not ledger_path.exists():
        return ()
    records: list[LearningRecord] = []
    previous_digest: str | None = None
    for expected_sequence, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            document = json.loads(line)
            raw_feedback = document["feedback"]
            feedback = LearningFeedback(
                feedback_id=raw_feedback["feedback_id"],
                source_manifest_digest=raw_feedback["source_manifest_digest"],
                finding_code=raw_feedback["finding_code"],
                kind=FeedbackKind(raw_feedback["kind"]),
                detail=raw_feedback["detail"],
                reviewer=raw_feedback["reviewer"],
                reviewer_role=ReviewerRole(raw_feedback["reviewer_role"]),
                review_receipt_digest=raw_feedback["review_receipt_digest"],
                reviewed_at=raw_feedback["reviewed_at"],
            )
            record = LearningRecord(
                sequence=document["sequence"],
                previous_digest=document["previous_digest"],
                feedback=feedback,
                record_digest=document["record_digest"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuditBotError("AUDIT_LEARNING_LEDGER_INVALID") from exc
        unsigned = {
            "sequence": record.sequence,
            "previous_digest": record.previous_digest,
            "feedback": _feedback_document(record.feedback),
        }
        if (
            record.sequence != expected_sequence
            or record.previous_digest != previous_digest
            or record.record_digest != _digest(unsigned)
        ):
            raise AuditBotError("AUDIT_LEARNING_LEDGER_TAMPERED")
        _validate_feedback(record.feedback)
        records.append(record)
        previous_digest = record.record_digest
    return tuple(records)


def propose_upgrade(
    records: tuple[LearningRecord, ...],
    *,
    request_id: str,
    minimum_confirmations: int = 2,
) -> dict[str, object] | None:
    """Create a non-executable improvement request; never mutate policy or code."""
    if minimum_confirmations < 2:
        raise AuditBotError("LEARNING_THRESHOLD_UNSAFE")
    grouped: dict[tuple[FeedbackKind, str], list[LearningRecord]] = {}
    for record in records:
        grouped.setdefault((record.feedback.kind, record.feedback.finding_code), []).append(record)
    eligible = [
        (key, values)
        for key, values in grouped.items()
        if key[0] in {FeedbackKind.FALSE_POSITIVE, FeedbackKind.MISSED_FINDING}
        and len(values) >= minimum_confirmations
        and {item.feedback.reviewer_role for item in values}
        >= {ReviewerRole.ARKAON, ReviewerRole.ETERNIAN}
    ]
    if not eligible:
        return None
    evidence_refs = sorted({item.record_digest for _, values in eligible for item in values})
    requested_changes = [
        {
            "feedback_kind": kind.value,
            "finding_code": code,
            "observation_count": len(values),
            "reviewer_roles": sorted({item.feedback.reviewer_role.value for item in values}),
        }
        for (kind, code), values in sorted(eligible, key=lambda item: (item[0][0], item[0][1]))
    ]
    body: dict[str, object] = {
        "schema_version": "apf.audit-bot-upgrade-proposal/1.0",
        "packet_type": "SELF_IMPROVEMENT_REQUEST",
        "request_id": request_id,
        "state": "PROPOSED_ONLY",
        "target": "ARKAON_AUDIT_BOT",
        "requested_changes": requested_changes,
        "evidence_refs": evidence_refs,
        "required_flow": [
            "OWNER_APPROVED",
            "SANDBOX_IMPLEMENTING",
            "ARKAON_VERIFYING",
            "ARKAON_VERIFIED",
            "ETERNIAN_AUDITING",
            "ETERNIAN_VERIFIED",
            "DEPLOYMENT_APPROVAL_PENDING",
        ],
        "automatic_policy_mutation": False,
        "automatic_merge": False,
        "automatic_deployment": False,
    }
    body["proposal_digest"] = _digest(body)
    return body


def _validate_feedback(feedback: LearningFeedback) -> None:
    if not all(
        (feedback.feedback_id, feedback.finding_code, feedback.detail, feedback.reviewer)
    ):
        raise AuditBotError("AUDIT_LEARNING_FEEDBACK_INCOMPLETE")
    if not feedback.source_manifest_digest.startswith("sha256:") or len(feedback.source_manifest_digest) != 71:
        raise AuditBotError("AUDIT_LEARNING_SOURCE_DIGEST_INVALID")
    if not feedback.review_receipt_digest.startswith("sha256:") or len(feedback.review_receipt_digest) != 71:
        raise AuditBotError("AUDIT_LEARNING_RECEIPT_DIGEST_INVALID")
    try:
        parsed = datetime.fromisoformat(feedback.reviewed_at)
    except ValueError as exc:
        raise AuditBotError("AUDIT_LEARNING_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise AuditBotError("AUDIT_LEARNING_TIMEZONE_REQUIRED")


def _feedback_document(feedback: LearningFeedback) -> dict[str, object]:
    value = asdict(feedback)
    value["kind"] = feedback.kind.value
    value["reviewer_role"] = feedback.reviewer_role.value
    return value


def _record_document(record: LearningRecord) -> dict[str, object]:
    return {
        "sequence": record.sequence,
        "previous_digest": record.previous_digest,
        "feedback": _feedback_document(record.feedback),
        "record_digest": record.record_digest,
    }


def _digest(document: dict[str, object]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()
