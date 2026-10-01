"""Periodic internal integrity audit for deployed ARKAON controls and ledgers."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from apf.arkaon_audit_bot import AuditBotError, AuditDecision
from apf.audit_bot_learning import LearningPolicy, load_feedback


@dataclass(frozen=True)
class InternalAuditResult:
    decision: AuditDecision
    findings: tuple[str, ...]
    evidence_digest: str


_OBJECT_ID = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")


def run_internal_integrity_audit(
    *,
    foundry_root: Path,
    repository_root: Path,
    policy_path: Path,
    baseline_path: Path,
) -> InternalAuditResult:
    findings: list[str] = []
    policy = _read_json(policy_path, "INTERNAL_AUDIT_POLICY_INVALID")
    protected_paths = policy.get("protected_paths")
    if not isinstance(protected_paths, list) or not protected_paths:
        raise AuditBotError("INTERNAL_AUDIT_PROTECTED_PATHS_INVALID")
    baseline = _optional_json(baseline_path)
    if baseline is None:
        findings.append("HOLD:DEPLOYMENT_BASELINE_MISSING")
    else:
        _check_baseline(repository_root, protected_paths, policy, baseline, findings)
    _check_owner_ledger(foundry_root / "state" / "owner-approvals.json", findings)
    _check_learning_ledger(foundry_root / "state" / "audit-bot-learning.jsonl", findings)
    _check_queues(foundry_root / "state", findings)
    decision = _decision(findings)
    unsigned = {
        "schema_version": "apf.audit-bot-internal-audit/1.0",
        "decision": decision.value,
        "findings": sorted(findings),
        "merge_allowed": False,
        "deployment_allowed": False,
    }
    evidence_digest = _digest(unsigned)
    result = {**unsigned, "evidence_digest": evidence_digest}
    _atomic_json(foundry_root / "state" / "audit-bot-internal-latest.json", result)
    return InternalAuditResult(decision, tuple(sorted(findings)), evidence_digest)


def create_deployment_baseline(
    *, repository_root: Path, policy_path: Path, deployed_commit_sha: str
) -> dict[str, object]:
    """Create a candidate baseline; owner deployment approval must persist it."""
    if _OBJECT_ID.fullmatch(deployed_commit_sha) is None:
        raise AuditBotError("DEPLOYMENT_BASELINE_COMMIT_INVALID")
    if _git_head(repository_root) != deployed_commit_sha:
        raise AuditBotError("DEPLOYMENT_BASELINE_HEAD_MISMATCH")
    policy = _read_json(policy_path, "INTERNAL_AUDIT_POLICY_INVALID")
    paths = policy.get("protected_paths")
    if not isinstance(paths, list) or not paths:
        raise AuditBotError("INTERNAL_AUDIT_PROTECTED_PATHS_INVALID")
    document: dict[str, object] = {
        "schema_version": "apf.audit-bot-deployment-baseline/1.0",
        "state": "DEPLOYMENT_APPROVAL_PENDING",
        "deployed_commit_sha": deployed_commit_sha,
        "policy_digest": _digest(policy),
        "protected_sha256": {
            path: _file_digest(repository_root / path) for path in sorted(paths)
        },
        "automatic_activation": False,
    }
    document["baseline_digest"] = _digest(document)
    return document


def persist_deployment_baseline(path: Path, document: dict[str, object]) -> None:
    """Durably create a baseline file without overwriting prior evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AuditBotError("DEPLOYMENT_BASELINE_ALREADY_EXISTS") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def activate_deployment_baseline_from_receipt(
    candidate: dict[str, object], receipt: dict[str, object]
) -> dict[str, object]:
    """Validate a GitHub-returned owner receipt and bind it to one candidate."""
    supplied = receipt.get("receipt_digest")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    if (
        receipt.get("schema_version") != "apf.deployment-approval-receipt/1.0"
        or receipt.get("decision") != "APPROVED"
        or receipt.get("baseline_digest") != candidate.get("baseline_digest")
        or supplied != _digest(unsigned)
    ):
        raise AuditBotError("DEPLOYMENT_APPROVAL_RECEIPT_INVALID")
    approver = receipt.get("approver")
    approved_at = receipt.get("approved_at")
    if not isinstance(approver, str) or not isinstance(approved_at, str):
        raise AuditBotError("DEPLOYMENT_APPROVAL_RECEIPT_INVALID")
    return activate_deployment_baseline(
        candidate,
        approver=approver,
        approved_at=approved_at,
        deployment_approval_digest=str(supplied),
    )


def activate_deployment_baseline(
    candidate: dict[str, object],
    *,
    approver: str,
    approved_at: str,
    deployment_approval_digest: str,
) -> dict[str, object]:
    """Bind an immutable baseline candidate to explicit owner deployment approval."""
    if candidate.get("state") != "DEPLOYMENT_APPROVAL_PENDING":
        raise AuditBotError("DEPLOYMENT_BASELINE_CANDIDATE_REQUIRED")
    supplied = candidate.get("baseline_digest")
    unsigned = {key: value for key, value in candidate.items() if key != "baseline_digest"}
    if supplied != _digest(unsigned):
        raise AuditBotError("DEPLOYMENT_BASELINE_TAMPERED")
    if not approver.strip() or not _DIGEST.fullmatch(deployment_approval_digest):
        raise AuditBotError("DEPLOYMENT_BASELINE_APPROVAL_INVALID")
    try:
        parsed = datetime.fromisoformat(approved_at)
    except ValueError as exc:
        raise AuditBotError("DEPLOYMENT_BASELINE_APPROVAL_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise AuditBotError("DEPLOYMENT_BASELINE_APPROVAL_TIMEZONE_REQUIRED")
    active = {
        **unsigned,
        "state": "ACTIVE",
        "approver": approver.strip(),
        "approved_at": approved_at,
        "deployment_approval_digest": deployment_approval_digest,
    }
    active["baseline_digest"] = _digest(active)
    return active


def _check_baseline(
    repository_root: Path,
    protected_paths: list[object],
    policy: dict[str, object],
    baseline: dict[str, object],
    findings: list[str],
) -> None:
    if (
        baseline.get("schema_version") != "apf.audit-bot-deployment-baseline/1.0"
        or baseline.get("state") != "ACTIVE"
    ):
        findings.append("BLOCKED:DEPLOYMENT_BASELINE_SCHEMA_INVALID")
        return
    deployed = baseline.get("deployed_commit_sha")
    expected = baseline.get("protected_sha256")
    baseline_digest = baseline.get("baseline_digest")
    unsigned = {key: value for key, value in baseline.items() if key != "baseline_digest"}
    if (
        not isinstance(deployed, str)
        or _OBJECT_ID.fullmatch(deployed) is None
        or not isinstance(expected, dict)
        or baseline_digest != _digest(unsigned)
    ):
        findings.append("BLOCKED:DEPLOYMENT_BASELINE_TAMPERED")
        return
    if baseline.get("policy_digest") != _digest(policy):
        findings.append("BLOCKED:AUDIT_POLICY_DRIFT")
    head = _git_head(repository_root)
    if head != deployed:
        findings.append("HOLD:DEPLOYED_HEAD_CHANGED")
    for raw_path in protected_paths:
        if not isinstance(raw_path, str):
            findings.append("BLOCKED:PROTECTED_PATH_INVALID")
            continue
        expected_digest = expected.get(raw_path)
        if not isinstance(expected_digest, str) or not _DIGEST.fullmatch(expected_digest):
            findings.append(f"BLOCKED:BASELINE_DIGEST_MISSING:{raw_path}")
            continue
        try:
            actual = _file_digest(repository_root / raw_path)
        except OSError:
            findings.append(f"BLOCKED:PROTECTED_FILE_MISSING:{raw_path}")
            continue
        if actual != expected_digest:
            findings.append(f"BLOCKED:PROTECTED_FILE_DRIFT:{raw_path}")


def _check_owner_ledger(path: Path, findings: list[str]) -> None:
    if not path.exists():
        return
    try:
        document = _read_json(path, "OWNER_APPROVAL_LEDGER_INVALID")
        entries = document.get("entries")
        if document.get("schema_version") != "apf.owner-approval-ledger/1.0" or not isinstance(entries, list):
            raise AuditBotError("OWNER_APPROVAL_LEDGER_INVALID")
        ids = [entry.get("request_id") for entry in entries if isinstance(entry, dict)]
        if len(ids) != len(entries) or len(ids) != len(set(ids)):
            raise AuditBotError("OWNER_APPROVAL_LEDGER_DUPLICATE")
        for entry in entries:
            receipt_digest = entry.get("receipt_digest")
            unsigned = {key: value for key, value in entry.items() if key != "receipt_digest"}
            actual = sha256(
                json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if receipt_digest != actual:
                raise AuditBotError("OWNER_APPROVAL_LEDGER_TAMPERED")
    except AuditBotError as exc:
        findings.append(f"BLOCKED:{exc}")


def _check_learning_ledger(path: Path, findings: list[str]) -> None:
    if not path.exists() and not path.with_name(path.name + ".segments").exists():
        return
    try:
        load_feedback(path, policy=LearningPolicy())
    except AuditBotError as exc:
        findings.append(f"BLOCKED:{exc}")


def _check_queues(state_root: Path, findings: list[str]) -> None:
    for directory in ("self-improvement-execution-queue", "self-improvement-audit-queue"):
        root = state_root / directory
        for path in sorted(root.glob("*.json")) if root.is_dir() else ():
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                findings.append(f"BLOCKED:QUEUE_JSON_INVALID:{path.name}")
                continue
            if document.get("merge_allowed") is not False and "merge_allowed" in document:
                findings.append(f"BLOCKED:QUEUE_MERGE_ESCALATION:{path.name}")
            if document.get("deployment_allowed") is not False and "deployment_allowed" in document:
                findings.append(f"BLOCKED:QUEUE_DEPLOYMENT_ESCALATION:{path.name}")


def _decision(findings: list[str]) -> AuditDecision:
    if any(item.startswith("BLOCKED:") for item in findings):
        return AuditDecision.BLOCKED
    if findings:
        return AuditDecision.HOLD
    return AuditDecision.PASS


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root.resolve()), "rev-parse", "HEAD"),
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or _OBJECT_ID.fullmatch(value) is None:
        raise AuditBotError("INTERNAL_AUDIT_HEAD_INVALID")
    return value


def _file_digest(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _optional_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return _read_json(path, "INTERNAL_AUDIT_JSON_INVALID")


def _read_json(path: Path, code: str) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditBotError(code) from exc
    if not isinstance(document, dict):
        raise AuditBotError(code)
    return document


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _digest(document: dict[str, object]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()
