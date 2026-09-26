"""Human-readable, scope-bound self-improvement approval reports."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field


class PlainApprovalError(RuntimeError):
    pass


_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_ALLOWED_OPERATIONS = frozenset(
    {"READ_WORKTREE", "WRITE_WORKTREE", "RUN_TESTS", "RUN_LINTER", "GENERATE_ARTIFACT",
     "CREATE_OPEN_UNMERGED_PR", "UPDATE_OPEN_UNMERGED_PR"}
)


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern=r"^(APPROVE|HOLD|REJECT)$")
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: UUID
    expires_at: datetime


def canonical_scope(document: dict[str, object]) -> dict[str, object]:
    keys = (
        "request_id", "intent_dna", "capability_gap", "evidence_refs", "proposed_change",
        "expected_benefit", "risks", "validation_plan", "source_tier",
    )
    try:
        return {key: document[key] for key in keys}
    except KeyError as exc:
        raise PlainApprovalError("PLAIN_REPORT_SCOPE_INCOMPLETE") from exc


def digest(document: dict[str, object]) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return sha256(encoded).hexdigest()


def validate_report(document: dict[str, object]) -> dict[str, object]:
    request_id = document.get("request_id")
    scope_digest = document.get("scope_digest")
    if not isinstance(request_id, str) or _ID.fullmatch(request_id) is None:
        raise PlainApprovalError("PLAIN_REPORT_REQUEST_ID_INVALID")
    if not isinstance(scope_digest, str) or _DIGEST.fullmatch(scope_digest) is None:
        raise PlainApprovalError("PLAIN_REPORT_SCOPE_DIGEST_INVALID")
    if digest(canonical_scope(document)) != scope_digest:
        raise PlainApprovalError("PLAIN_REPORT_SCOPE_TAMPERED")
    if document.get("state") != "APPROVAL_PENDING":
        raise PlainApprovalError("PLAIN_REPORT_NOT_PENDING")
    for key in ("production_change_allowed", "automatic_merge_allowed", "deployment_allowed"):
        if document.get(key) is not False:
            raise PlainApprovalError("PLAIN_REPORT_SAFETY_BOUNDARY_REQUIRED")

    plain = document.get("plain_language")
    if not isinstance(plain, dict) or plain.get("scope_digest") != scope_digest:
        raise PlainApprovalError("PLAIN_REPORT_EXPLANATION_UNBOUND")
    for key in ("title", "problem", "change", "benefit", "impact", "rollback"):
        if not isinstance(plain.get(key), str) or not plain[key].strip():
            raise PlainApprovalError("PLAIN_REPORT_EXPLANATION_INCOMPLETE")
    risks = plain.get("risks")
    if not isinstance(risks, list) or not risks or not all(isinstance(x, str) and x for x in risks):
        raise PlainApprovalError("PLAIN_REPORT_RISKS_INCOMPLETE")
    visual = plain.get("visual")
    if not isinstance(visual, dict):
        raise PlainApprovalError("PLAIN_REPORT_VISUAL_INCOMPLETE")
    for key in ("before", "after"):
        steps = visual.get(key)
        if not isinstance(steps, list) or not steps or not all(
            isinstance(x, str) and x.strip() for x in steps
        ):
            raise PlainApprovalError("PLAIN_REPORT_VISUAL_INCOMPLETE")

    review = document.get("semantic_review")
    if not isinstance(review, dict) or review.get("state") != "ETERNIAN_VERIFIED":
        raise PlainApprovalError("PLAIN_REPORT_SEMANTIC_REVIEW_REQUIRED")
    if review.get("reviewer_role") != "ETERNIAN":
        raise PlainApprovalError("PLAIN_REPORT_INDEPENDENT_REVIEW_REQUIRED")
    if review.get("scope_digest") != scope_digest or review.get("plain_digest") != digest(plain):
        raise PlainApprovalError("PLAIN_REPORT_SEMANTIC_BINDING_MISMATCH")
    supplied_review_digest = review.get("review_digest")
    unsigned_review = {key: value for key, value in review.items() if key != "review_digest"}
    if supplied_review_digest != digest(unsigned_review):
        raise PlainApprovalError("PLAIN_REPORT_SEMANTIC_REVIEW_TAMPERED")

    approval_scope = document.get("approval_scope")
    if not isinstance(approval_scope, dict):
        raise PlainApprovalError("PLAIN_REPORT_APPROVAL_SCOPE_REQUIRED")
    paths = approval_scope.get("allowed_paths")
    operations = approval_scope.get("allowed_operations")
    if not isinstance(paths, list) or not paths or not all(_safe_path(path) for path in paths):
        raise PlainApprovalError("PLAIN_REPORT_ALLOWED_PATHS_INVALID")
    if not isinstance(operations, list) or not operations or not set(operations) <= _ALLOWED_OPERATIONS:
        raise PlainApprovalError("PLAIN_REPORT_ALLOWED_OPERATIONS_INVALID")
    return document


class PlainLanguageApprovalStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_reports(self) -> list[dict[str, object]]:
        result = []
        report_root = self.root / "state" / "plain-language-approval-reports"
        for path in sorted(report_root.glob("*.json")) if report_root.is_dir() else ():
            try:
                report = validate_report(_object(path))
            except PlainApprovalError:
                continue
            result.append(_public_report(report, detail=False))
        return result

    def get_report(self, request_id: str) -> dict[str, object]:
        if _ID.fullmatch(request_id) is None:
            raise PlainApprovalError("PLAIN_REPORT_REQUEST_ID_INVALID")
        report = validate_report(
            _object(self.root / "state" / "plain-language-approval-reports" / f"{request_id}.json")
        )
        return _public_report(report, detail=True)

    def decide(
        self, *, request_id: str, decision: ApprovalDecision, principal_id: str,
        now: datetime | None = None,
    ) -> dict[str, object]:
        now = now or datetime.now(UTC)
        if (
            decision.expires_at.tzinfo is None
            or now >= decision.expires_at
            or decision.expires_at > now + timedelta(minutes=10)
        ):
            raise PlainApprovalError("PLAIN_APPROVAL_EXPIRED")
        report = validate_report(
            _object(self.root / "state" / "plain-language-approval-reports" / f"{request_id}.json")
        )
        if decision.scope_digest != report["scope_digest"]:
            raise PlainApprovalError("PLAIN_APPROVAL_SCOPE_MISMATCH")
        path = self.root / "state" / "plain-language-approval-receipts" / f"{request_id}.json"
        if path.exists():
            existing = _object(path)
            if (
                existing.get("nonce") == str(decision.nonce)
                and existing.get("decision") == decision.decision
                and existing.get("scope_digest") == decision.scope_digest
                and existing.get("approver_principal_id") == principal_id
            ):
                return existing
            raise PlainApprovalError("PLAIN_APPROVAL_ALREADY_DECIDED")
        receipt = {
            "schema_version": "apf.plain-language-approval-receipt/1.0",
            "request_id": request_id,
            "scope_digest": report["scope_digest"],
            "plain_digest": digest(report["plain_language"]),
            "decision": decision.decision,
            "approver_principal_id": principal_id,
            "approved_at": now.isoformat(),
            "expires_at": decision.expires_at.isoformat(),
            "nonce": str(decision.nonce),
            "production_change_allowed": False,
            "automatic_merge_allowed": False,
            "deployment_allowed": False,
        }
        receipt["receipt_digest"] = digest(receipt)
        _exclusive_json(path, receipt)
        return receipt


def _public_report(document: dict[str, object], *, detail: bool) -> dict[str, object]:
    plain = document["plain_language"]
    assert isinstance(plain, dict)
    value = {
        "request_id": document["request_id"], "scope_digest": document["scope_digest"],
        "title": plain["title"], "risk_level": plain.get("risk_level", "확인 필요"),
        "automatic_merge_allowed": False, "deployment_allowed": False,
    }
    if detail:
        value.update({"plain_language": plain, "approval_scope": document["approval_scope"]})
    return value


def _safe_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlainApprovalError("PLAIN_REPORT_UNAVAILABLE") from exc
    if not isinstance(value, dict):
        raise PlainApprovalError("PLAIN_REPORT_INVALID")
    return value


def _exclusive_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        existing = _object(path)
        if existing.get("nonce") == document.get("nonce") and existing == document:
            return
        raise PlainApprovalError("PLAIN_APPROVAL_ALREADY_DECIDED") from exc
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
