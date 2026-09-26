"""Deterministic, read-only audit gate for ARKAON self-improvement changes."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol


class AuditBotError(ValueError):
    pass


class AuditDecision(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"
    BLOCKED = "BLOCKED"


class Severity(StrEnum):
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AuditFinding:
    code: str
    severity: Severity
    path: str
    detail: str


@dataclass(frozen=True)
class ChangeReport:
    request_id: str
    scope_digest: str
    reported_changed_paths: tuple[str, ...]
    intent_dna_refs: tuple[str, ...]
    test_evidence_sha256: tuple[str, ...]


@dataclass(frozen=True)
class AuditManifest:
    schema_version: str
    request_id: str
    scope_digest: str
    base_sha: str
    candidate_sha: str
    decision: AuditDecision
    findings: tuple[AuditFinding, ...]
    actual_changed_paths: tuple[str, ...]
    config_digest: str
    evidence_digest: str
    merge_allowed: bool = False
    deployment_allowed: bool = False

    def document(self, *, include_evidence_digest: bool = True) -> dict[str, object]:
        value = asdict(self)
        value["decision"] = self.decision.value
        value["findings"] = [
            {**asdict(finding), "severity": finding.severity.value}
            for finding in self.findings
        ]
        value["actual_changed_paths"] = list(self.actual_changed_paths)
        if not include_evidence_digest:
            value.pop("evidence_digest")
        return value


class RevisionReader(Protocol):
    def changed_paths(self, base_sha: str, candidate_sha: str) -> tuple[str, ...]: ...

    def read(self, revision: str, path: str) -> bytes | None: ...


_OBJECT_ID = re.compile(r"\A[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
_DIGEST = re.compile(r"\A(?:sha256:)?[0-9a-f]{64}\Z")


class GitRevisionReader:
    """Read only validated revisions and repository-relative paths through git."""

    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()

    def changed_paths(self, base_sha: str, candidate_sha: str) -> tuple[str, ...]:
        _validate_object_id(base_sha)
        _validate_object_id(candidate_sha)
        completed = self._run("diff", "--name-only", "--diff-filter=ACDMRTUXB", base_sha, candidate_sha)
        return tuple(sorted({_validate_path(line) for line in completed.stdout.splitlines() if line}))

    def read(self, revision: str, path: str) -> bytes | None:
        _validate_object_id(revision)
        safe_path = _validate_path(path)
        completed = subprocess.run(
            ("git", "-C", str(self.repository_root), "show", f"{revision}:{safe_path}"),
            capture_output=True,
            check=False,
        )
        if completed.returncode == 128:
            return None
        if completed.returncode != 0:
            raise AuditBotError("GIT_READ_FAILED")
        return completed.stdout

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ("git", "-C", str(self.repository_root), *arguments),
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AuditBotError("GIT_DIFF_FAILED")
        return completed


def load_change_report(path: Path) -> ChangeReport:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditBotError("CHANGE_REPORT_INVALID") from exc
    if document.get("schema_version") != "apf.arkaon-change-report/1.0":
        raise AuditBotError("CHANGE_REPORT_SCHEMA_INVALID")
    request_id = _required_string(document, "request_id")
    scope_digest = _required_digest(document, "scope_digest")
    return ChangeReport(
        request_id=request_id,
        scope_digest=scope_digest.removeprefix("sha256:"),
        reported_changed_paths=_path_list(document, "reported_changed_paths"),
        intent_dna_refs=_path_list(document, "intent_dna_refs", required=False),
        test_evidence_sha256=_digest_list(document, "test_evidence_sha256"),
    )


def run_audit(
    *,
    reader: RevisionReader,
    base_sha: str,
    candidate_sha: str,
    report: ChangeReport,
    policy_document: dict[str, object],
    approved_scope_digest: str,
    approved_paths: tuple[str, ...],
) -> AuditManifest:
    _validate_object_id(base_sha)
    _validate_object_id(candidate_sha)
    policy = _validate_policy(policy_document)
    actual_paths = reader.changed_paths(base_sha, candidate_sha)
    findings: list[AuditFinding] = []

    normalized_digest = approved_scope_digest.removeprefix("sha256:")
    if _DIGEST.fullmatch(normalized_digest) is None:
        raise AuditBotError("APPROVED_SCOPE_DIGEST_INVALID")
    safe_approved_paths = tuple(_validate_path(path) for path in approved_paths)
    if not safe_approved_paths:
        raise AuditBotError("APPROVED_PATHS_REQUIRED")
    if report.scope_digest != normalized_digest:
        findings.append(
            _finding(
                "SCOPE_DIGEST_MISMATCH",
                Severity.CRITICAL,
                ".",
                "change report is not bound to the owner-approved scope",
            )
        )
    for path in actual_paths:
        if not any(path == allowed or path.startswith(allowed.rstrip("/") + "/") for allowed in safe_approved_paths):
            findings.append(
                _finding(
                    "CHANGE_OUTSIDE_APPROVED_SCOPE",
                    Severity.CRITICAL,
                    path,
                    "actual diff path is outside owner-approved paths",
                )
            )

    actual = set(actual_paths)
    reported = set(report.reported_changed_paths)
    for path in sorted(actual - reported):
        findings.append(_finding("UNREPORTED_CHANGE", Severity.HIGH, path, "actual diff omitted from report"))
    for path in sorted(reported - actual):
        findings.append(_finding("PHANTOM_REPORTED_CHANGE", Severity.MEDIUM, path, "report claims a path absent from diff"))

    protected = set(policy["protected_paths"])
    for path in sorted(actual & protected):
        before = reader.read(base_sha, path)
        after = reader.read(candidate_sha, path)
        if after is None:
            findings.append(_finding("PROTECTED_CONTROL_DELETED", Severity.CRITICAL, path, "protected control was deleted"))
        elif before != after:
            findings.append(_finding("PROTECTED_CONTROL_CHANGED", Severity.HIGH, path, "independent review is required"))

    for path in actual_paths:
        content = reader.read(candidate_sha, path)
        if content is None or not path.endswith(".json"):
            continue
        try:
            document = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            findings.append(_finding("CHANGED_JSON_INVALID", Severity.HIGH, path, "changed JSON cannot be parsed"))
            continue
        findings.extend(_resource_findings(path, document, set(policy["bounded_keys"])))
        findings.extend(_machine_path_findings(path, document, set(policy["portable_path_keys"])))

    intent_prefixes = tuple(policy["intent_sensitive_prefixes"])
    if any(path.startswith(intent_prefixes) for path in actual_paths) and not report.intent_dna_refs:
        findings.append(_finding("INTENT_DNA_EVIDENCE_MISSING", Severity.HIGH, ".", "intent-sensitive changes require Intent_DNA references"))
    if not report.test_evidence_sha256:
        findings.append(_finding("TEST_EVIDENCE_MISSING", Severity.HIGH, ".", "SHA-256 test evidence is required"))

    findings_tuple = tuple(sorted(findings, key=lambda item: (item.severity, item.code, item.path)))
    decision = _decision(findings_tuple)
    config_digest = _sha256_document(policy_document)
    unsigned = {
        "schema_version": "apf.arkaon-audit-manifest/1.0",
        "request_id": report.request_id,
        "scope_digest": report.scope_digest,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "decision": decision.value,
        "findings": [
            {"code": item.code, "severity": item.severity.value, "path": item.path, "detail": item.detail}
            for item in findings_tuple
        ],
        "actual_changed_paths": list(actual_paths),
        "config_digest": config_digest,
        "merge_allowed": False,
        "deployment_allowed": False,
    }
    return AuditManifest(
        schema_version="apf.arkaon-audit-manifest/1.0",
        request_id=report.request_id,
        scope_digest=report.scope_digest,
        base_sha=base_sha,
        candidate_sha=candidate_sha,
        decision=decision,
        findings=findings_tuple,
        actual_changed_paths=actual_paths,
        config_digest=config_digest,
        evidence_digest=_sha256_document(unsigned),
    )


def write_manifest(path: Path, manifest: AuditManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest.document(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _resource_findings(path: str, value: object, bounded_keys: set[str], prefix: str = "") -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else key
            if key in bounded_keys and (child is None or isinstance(child, (int, float)) and child <= 0):
                findings.append(_finding("UNBOUNDED_RESOURCE_LIMIT", Severity.CRITICAL, path, location))
            if key.startswith("unbounded") and child is True:
                findings.append(_finding("UNBOUNDED_MODE_ENABLED", Severity.CRITICAL, path, location))
            findings.extend(_resource_findings(path, child, bounded_keys, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_resource_findings(path, child, bounded_keys, f"{prefix}[{index}]"))
    return findings


def _machine_path_findings(path: str, value: object, keys: set[str], prefix: str = "") -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else key
            if key in keys and isinstance(child, str) and _is_machine_absolute(child):
                findings.append(_finding("MACHINE_SPECIFIC_ABSOLUTE_PATH", Severity.HIGH, path, location))
            findings.extend(_machine_path_findings(path, child, keys, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_machine_path_findings(path, child, keys, f"{prefix}[{index}]"))
    return findings


def _is_machine_absolute(value: str) -> bool:
    if value.startswith("${"):
        return False
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _decision(findings: tuple[AuditFinding, ...]) -> AuditDecision:
    if any(item.severity == Severity.CRITICAL for item in findings):
        return AuditDecision.BLOCKED
    if findings:
        return AuditDecision.HOLD
    return AuditDecision.PASS


def _validate_policy(document: dict[str, object]) -> dict[str, list[str]]:
    if document.get("schema_version") != "apf.arkaon-audit-policy/1.0":
        raise AuditBotError("AUDIT_POLICY_SCHEMA_INVALID")
    keys = ("protected_paths", "bounded_keys", "portable_path_keys", "intent_sensitive_prefixes")
    return {key: list(_string_list(document, key)) for key in keys}


def _finding(code: str, severity: Severity, path: str, detail: str) -> AuditFinding:
    return AuditFinding(code=code, severity=severity, path=path, detail=detail)


def _validate_object_id(value: str) -> None:
    if _OBJECT_ID.fullmatch(value) is None:
        raise AuditBotError("GIT_OBJECT_ID_INVALID")


def _validate_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts or normalized.startswith(".git/"):
        raise AuditBotError("UNSAFE_REPOSITORY_PATH")
    return candidate.as_posix()


def _required_string(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise AuditBotError(f"{key.upper()}_REQUIRED")
    return value


def _required_digest(document: dict[str, object], key: str) -> str:
    value = _required_string(document, key)
    if _DIGEST.fullmatch(value) is None:
        raise AuditBotError(f"{key.upper()}_INVALID")
    return value


def _string_list(document: dict[str, object], key: str, *, required: bool = True) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or (required and not value) or any(not isinstance(item, str) or not item for item in value):
        raise AuditBotError(f"{key.upper()}_INVALID")
    return tuple(value)


def _path_list(document: dict[str, object], key: str, *, required: bool = True) -> tuple[str, ...]:
    return tuple(_validate_path(item) for item in _string_list(document, key, required=required))


def _digest_list(document: dict[str, object], key: str) -> tuple[str, ...]:
    values = _string_list(document, key, required=False)
    if any(_DIGEST.fullmatch(item) is None for item in values):
        raise AuditBotError(f"{key.upper()}_INVALID")
    return values


def _sha256_document(document: dict[str, object]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()
