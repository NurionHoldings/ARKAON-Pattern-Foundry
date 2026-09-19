"""Tamper-evident, bounded learning feedback for ARKAON Audit Bot."""

from __future__ import annotations

import json
import os
import re
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


@dataclass(frozen=True)
class LearningPolicy:
    max_records_per_segment: int = 500
    max_segments: int = 20
    minimum_confirmations: int = 2


_SHA256 = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
DEFAULT_LEARNING_POLICY = LearningPolicy()


def append_feedback(
    ledger_path: Path,
    feedback: LearningFeedback,
    *,
    receipt_registry_path: Path,
    policy: LearningPolicy = DEFAULT_LEARNING_POLICY,
) -> LearningRecord:
    """Append once under an exclusive lock and rotate bounded immutable segments."""
    _validate_policy(policy)
    _validate_feedback(feedback)
    _validate_receipt_binding(receipt_registry_path, feedback)
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = _acquire_lock(lock_path)
    try:
        records = load_feedback(ledger_path, policy=policy)
        if any(record.feedback.feedback_id == feedback.feedback_id for record in records):
            raise AuditBotError("AUDIT_LEARNING_FEEDBACK_DUPLICATE")
        if any(
            record.feedback.review_receipt_digest == feedback.review_receipt_digest
            for record in records
        ):
            raise AuditBotError("AUDIT_LEARNING_RECEIPT_REUSED")
        current_count = _current_record_count(ledger_path)
        if current_count >= policy.max_records_per_segment:
            _rotate(ledger_path, records[-1], policy)
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
        with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(_record_document(record), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def load_feedback(
    ledger_path: Path, *, policy: LearningPolicy = DEFAULT_LEARNING_POLICY
) -> tuple[LearningRecord, ...]:
    _validate_policy(policy)
    sources = _segment_paths(ledger_path) + ([ledger_path] if ledger_path.exists() else [])
    records: list[LearningRecord] = []
    previous_digest: str | None = None
    for source in sources:
        for line in source.read_text(encoding="utf-8").splitlines():
            record = _parse_record(line)
            expected_sequence = len(records) + 1
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
    feedback_ids = [record.feedback.feedback_id for record in records]
    receipt_digests = [record.feedback.review_receipt_digest for record in records]
    if len(feedback_ids) != len(set(feedback_ids)):
        raise AuditBotError("AUDIT_LEARNING_FEEDBACK_DUPLICATE")
    if len(receipt_digests) != len(set(receipt_digests)):
        raise AuditBotError("AUDIT_LEARNING_RECEIPT_REUSED")
    return tuple(records)


def propose_upgrade(
    records: tuple[LearningRecord, ...],
    *,
    request_id: str,
    minimum_confirmations: int = 2,
) -> dict[str, object] | None:
    if _SAFE_ID.fullmatch(request_id) is None:
        raise AuditBotError("LEARNING_REQUEST_ID_INVALID")
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
        and len({item.feedback.review_receipt_digest for item in values}) >= minimum_confirmations
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


def _validate_receipt_binding(path: Path, feedback: LearningFeedback) -> None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditBotError("AUDIT_REVIEW_RECEIPT_REGISTRY_INVALID") from exc
    if document.get("schema_version") != "apf.audit-review-receipt-registry/1.0":
        raise AuditBotError("AUDIT_REVIEW_RECEIPT_REGISTRY_INVALID")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise AuditBotError("AUDIT_REVIEW_RECEIPT_REGISTRY_INVALID")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("receipt_digest") == feedback.review_receipt_digest
    ]
    if len(matches) != 1:
        raise AuditBotError("AUDIT_REVIEW_RECEIPT_NOT_UNIQUE")
    entry = matches[0]
    expected = {
        "reviewer": feedback.reviewer,
        "reviewer_role": feedback.reviewer_role.value,
        "source_manifest_digest": feedback.source_manifest_digest,
        "finding_code": feedback.finding_code,
        "feedback_kind": feedback.kind.value,
    }
    if any(entry.get(key) != value for key, value in expected.items()):
        raise AuditBotError("AUDIT_REVIEW_RECEIPT_BINDING_MISMATCH")
    if not _SHA256.fullmatch(str(entry.get("evidence_digest", ""))):
        raise AuditBotError("AUDIT_REVIEW_RECEIPT_EVIDENCE_INVALID")


def _rotate(ledger_path: Path, last: LearningRecord, policy: LearningPolicy) -> None:
    archive = ledger_path.parent / f"{ledger_path.name}.segments"
    archive.mkdir(parents=True, exist_ok=True)
    segments = _segment_paths(ledger_path)
    if len(segments) >= policy.max_segments:
        raise AuditBotError("AUDIT_LEARNING_BACKPRESSURE")
    start = last.sequence - _current_record_count(ledger_path) + 1
    target = archive / f"{start:012d}-{last.sequence:012d}-{last.record_digest[7:19]}.jsonl"
    if target.exists():
        raise AuditBotError("AUDIT_LEARNING_SEGMENT_CONFLICT")
    ledger_path.replace(target)


def _segment_paths(ledger_path: Path) -> list[Path]:
    archive = ledger_path.parent / f"{ledger_path.name}.segments"
    return sorted(archive.glob("*.jsonl")) if archive.is_dir() else []


def _current_record_count(ledger_path: Path) -> int:
    return len(ledger_path.read_text(encoding="utf-8").splitlines()) if ledger_path.exists() else 0


def _acquire_lock(path: Path) -> int:
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AuditBotError("AUDIT_LEARNING_LEDGER_BUSY") from exc
    os.write(descriptor, str(os.getpid()).encode())
    return descriptor


def _parse_record(line: str) -> LearningRecord:
    try:
        document = json.loads(line)
        raw = document["feedback"]
        feedback = LearningFeedback(
            feedback_id=raw["feedback_id"],
            source_manifest_digest=raw["source_manifest_digest"],
            finding_code=raw["finding_code"],
            kind=FeedbackKind(raw["kind"]),
            detail=raw["detail"],
            reviewer=raw["reviewer"],
            reviewer_role=ReviewerRole(raw["reviewer_role"]),
            review_receipt_digest=raw["review_receipt_digest"],
            reviewed_at=raw["reviewed_at"],
        )
        return LearningRecord(
            sequence=document["sequence"],
            previous_digest=document["previous_digest"],
            feedback=feedback,
            record_digest=document["record_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuditBotError("AUDIT_LEARNING_LEDGER_INVALID") from exc


def _validate_policy(policy: LearningPolicy) -> None:
    if (
        policy.max_records_per_segment < 2
        or policy.max_segments < 1
        or policy.minimum_confirmations < 2
    ):
        raise AuditBotError("AUDIT_LEARNING_POLICY_UNSAFE")


def _validate_feedback(feedback: LearningFeedback) -> None:
    if _SAFE_ID.fullmatch(feedback.feedback_id) is None or not all(
        (feedback.finding_code, feedback.detail, feedback.reviewer)
    ):
        raise AuditBotError("AUDIT_LEARNING_FEEDBACK_INCOMPLETE")
    if not _SHA256.fullmatch(feedback.source_manifest_digest):
        raise AuditBotError("AUDIT_LEARNING_SOURCE_DIGEST_INVALID")
    if not _SHA256.fullmatch(feedback.review_receipt_digest):
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
