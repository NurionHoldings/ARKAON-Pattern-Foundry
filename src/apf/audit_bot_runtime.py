"""Automatic fail-closed ARKAON Audit Bot queue processor."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

from apf.arkaon_audit_bot import (
    AuditBotError,
    AuditDecision,
    GitRevisionReader,
    load_change_report,
    run_audit,
    write_manifest,
)


@dataclass(frozen=True)
class AuditQueueResult:
    passed: tuple[str, ...]
    held: tuple[str, ...]
    blocked: tuple[str, ...]


_REQUEST_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_OBJECT_ID = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def enqueue_verified_change(
    *,
    foundry_root: Path,
    request_id: str,
    scope_digest: str,
    base_sha: str,
    candidate_sha: str,
    change_report_path: str,
    arkaon_test_evidence_digest: str,
) -> Path:
    """Atomically connect ARKAON verification to the mandatory audit gate."""
    if _REQUEST_ID.fullmatch(request_id) is None:
        raise AuditBotError("AUDIT_JOB_REQUEST_ID_INVALID")
    if _DIGEST.fullmatch(scope_digest) is None:
        raise AuditBotError("AUDIT_JOB_SCOPE_INVALID")
    if _OBJECT_ID.fullmatch(base_sha) is None or _OBJECT_ID.fullmatch(candidate_sha) is None:
        raise AuditBotError("AUDIT_JOB_REVISION_INVALID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", arkaon_test_evidence_digest):
        raise AuditBotError("ARKAON_TEST_EVIDENCE_INVALID")
    relative_report = _relative(change_report_path)
    job: dict[str, object] = {
        "schema_version": "apf.arkaon-audit-job/1.0",
        "state": "ARKAON_VERIFIED",
        "request_id": request_id,
        "scope_digest": scope_digest,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "change_report_path": relative_report,
        "arkaon_test_evidence_digest": arkaon_test_evidence_digest,
        "merge_allowed": False,
        "deployment_allowed": False,
    }
    path = (
        foundry_root.resolve()
        / "state"
        / "self-improvement-audit-queue"
        / f"{request_id}.json"
    )
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != job:
            raise AuditBotError("AUDIT_JOB_CONFLICT")
        return path
    _atomic_json(path, job)
    return path


def process_audit_queue(
    *,
    foundry_root: Path,
    repository_root: Path,
    policy_path: Path,
    max_jobs: int = 10,
) -> AuditQueueResult:
    """Process verified jobs without granting merge or deployment authority."""
    if max_jobs < 1 or max_jobs > 30:
        raise AuditBotError("AUDIT_QUEUE_BATCH_INVALID")
    root = foundry_root.resolve()
    queue_root = root / "state" / "self-improvement-audit-queue"
    lock_path = root / "state" / "audit-bot-runtime.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = _acquire_lock(lock_path)
    passed: list[str] = []
    held: list[str] = []
    blocked: list[str] = []
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        reader = GitRevisionReader(repository_root)
        paths = sorted(queue_root.glob("*.json"))[:max_jobs] if queue_root.is_dir() else []
        for path in paths:
            try:
                job = _load_job(path)
                request_id = job["request_id"]
                approval = _load_bound_approval(root, request_id, job["scope_digest"])
                report_path = _within(root, job["change_report_path"])
                manifest = run_audit(
                    reader=reader,
                    base_sha=job["base_sha"],
                    candidate_sha=job["candidate_sha"],
                    report=load_change_report(report_path),
                    policy_document=policy,
                    approved_scope_digest=approval["scope_digest"],
                    approved_paths=tuple(approval["allowed_paths"]),
                )
                manifest_path = root / "state" / "audit-manifests" / f"{request_id}.json"
                write_manifest(manifest_path, manifest)
                next_state = {
                    AuditDecision.PASS: "ETERNIAN_AUDIT_REQUIRED",
                    AuditDecision.HOLD: "HOLD",
                    AuditDecision.BLOCKED: "BLOCKED",
                }[manifest.decision]
                _atomic_json(
                    path,
                    {
                        **job,
                        "state": next_state,
                        "audit_manifest_path": manifest_path.relative_to(root).as_posix(),
                        "audit_manifest_digest": manifest.evidence_digest,
                        "merge_allowed": False,
                        "deployment_allowed": False,
                    },
                )
                target = {
                    AuditDecision.PASS: passed,
                    AuditDecision.HOLD: held,
                    AuditDecision.BLOCKED: blocked,
                }[manifest.decision]
                target.append(request_id)
            except (AuditBotError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                request_id = path.stem
                blocked.append(request_id)
                _quarantine_job(root, path, str(exc) or type(exc).__name__.upper())
        result = AuditQueueResult(tuple(passed), tuple(held), tuple(blocked))
        _atomic_json(
            root / "state" / "audit-bot-runtime-latest.json",
            {
                "schema_version": "apf.audit-bot-runtime-result/1.0",
                **asdict(result),
                "merge_automatic": False,
                "deployment_automatic": False,
            },
        )
        return result
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def _load_job(path: Path) -> dict[str, str | bool]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "apf.arkaon-audit-job/1.0":
        raise AuditBotError("AUDIT_JOB_SCHEMA_INVALID")
    if document.get("state") != "ARKAON_VERIFIED":
        raise AuditBotError("ARKAON_VERIFIED_JOB_REQUIRED")
    if document.get("merge_allowed") is not False or document.get("deployment_allowed") is not False:
        raise AuditBotError("AUDIT_JOB_AUTHORITY_ESCALATION")
    request_id = document.get("request_id")
    scope_digest = document.get("scope_digest")
    base_sha = document.get("base_sha")
    candidate_sha = document.get("candidate_sha")
    report_path = document.get("change_report_path")
    test_evidence = document.get("arkaon_test_evidence_digest")
    if not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None:
        raise AuditBotError("AUDIT_JOB_REQUEST_ID_INVALID")
    if not isinstance(scope_digest, str) or _DIGEST.fullmatch(scope_digest) is None:
        raise AuditBotError("AUDIT_JOB_SCOPE_INVALID")
    if not isinstance(base_sha, str) or _OBJECT_ID.fullmatch(base_sha) is None:
        raise AuditBotError("AUDIT_JOB_BASE_INVALID")
    if not isinstance(candidate_sha, str) or _OBJECT_ID.fullmatch(candidate_sha) is None:
        raise AuditBotError("AUDIT_JOB_CANDIDATE_INVALID")
    if not isinstance(report_path, str):
        raise AuditBotError("AUDIT_JOB_REPORT_REQUIRED")
    if not isinstance(test_evidence, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", test_evidence
    ):
        raise AuditBotError("ARKAON_TEST_EVIDENCE_INVALID")
    return {
        "schema_version": "apf.arkaon-audit-job/1.0",
        "state": "ARKAON_VERIFIED",
        "request_id": request_id,
        "scope_digest": scope_digest,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "change_report_path": _relative(report_path),
        "arkaon_test_evidence_digest": test_evidence,
        "merge_allowed": False,
        "deployment_allowed": False,
    }


def _load_bound_approval(root: Path, request_id: str, scope_digest: str) -> dict[str, object]:
    queue_path = root / "state" / "self-improvement-execution-queue" / f"{request_id}.json"
    ledger_path = root / "state" / "owner-approvals.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if (
        queue.get("schema_version") != "apf.approved-execution-job/1.0"
        or queue.get("state") != "OWNER_APPROVED"
        or queue.get("request_id") != request_id
        or queue.get("scope_digest") != scope_digest
    ):
        raise AuditBotError("AUDIT_APPROVAL_QUEUE_MISMATCH")
    entries = ledger.get("entries") if ledger.get("schema_version") == "apf.owner-approval-ledger/1.0" else None
    matches = [
        entry
        for entry in entries or []
        if isinstance(entry, dict)
        and entry.get("request_id") == request_id
        and entry.get("scope_digest") == scope_digest
        and entry.get("receipt_digest") == queue.get("receipt_digest")
        and entry.get("source_commit_sha") == queue.get("source_commit_sha")
    ]
    if len(matches) != 1:
        raise AuditBotError("AUDIT_APPROVAL_LEDGER_BINDING_FAILED")
    paths = matches[0].get("allowed_paths")
    if not isinstance(paths, list) or not paths:
        raise AuditBotError("AUDIT_APPROVED_PATHS_INVALID")
    return matches[0]


def _quarantine_job(root: Path, path: Path, reason: str) -> None:
    content = path.read_bytes()
    digest = sha256(content).hexdigest()
    quarantine = root / "quarantine" / "audit-bot"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / f"{path.stem}-{digest[:12]}.json"
    if target.exists() and target.read_bytes() != content:
        raise AuditBotError("AUDIT_QUARANTINE_COLLISION")
    if not target.exists():
        path.replace(target)
    else:
        path.unlink()
    _atomic_json(
        target.with_suffix(".blocked.json"),
        {
            "schema_version": "apf.audit-bot-quarantine/1.0",
            "state": "BLOCKED",
            "reason": reason,
            "evidence_digest": f"sha256:{digest}",
            "merge_allowed": False,
            "deployment_allowed": False,
        },
    )


def _within(root: Path, relative: str) -> Path:
    candidate = (root / _relative(relative)).resolve()
    if not candidate.is_relative_to(root):
        raise AuditBotError("AUDIT_PATH_ESCAPE")
    return candidate


def _relative(value: str) -> str:
    candidate = PurePosixPath(value.replace("\\", "/"))
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise AuditBotError("AUDIT_RELATIVE_PATH_INVALID")
    return candidate.as_posix()


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _acquire_lock(path: Path) -> int:
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AuditBotError("AUDIT_RUNTIME_ALREADY_RUNNING") from exc
    os.write(descriptor, str(os.getpid()).encode())
    return descriptor
