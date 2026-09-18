"""Owner-approved receipt ingestion and confined git-worktree execution."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol


class ApprovalExecutionError(RuntimeError):
    pass


_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_GIT_OBJECT_ID = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_REQUEST_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
_ALLOWED_EXECUTABLES = frozenset(
    {"python", "python.exe", "pytest", "pytest.exe", "ruff", "ruff.exe"}
)


@dataclass(frozen=True)
class OwnerApprovalReceipt:
    request_id: str
    scope_digest: str
    approver: str
    approved_at: str
    allowed_paths: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    source_commit_sha: str

    def canonical_document(self) -> dict[str, object]:
        document = asdict(self)
        document["allowed_paths"] = list(self.allowed_paths)
        document["allowed_operations"] = list(self.allowed_operations)
        return document

    def digest(self) -> str:
        encoded = json.dumps(
            self.canonical_document(), sort_keys=True, separators=(",", ":")
        ).encode()
        return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class WorktreeRunResult:
    request_id: str
    worktree_path: str
    base_sha: str
    receipt_digest: str
    command: tuple[str, ...]
    returncode: int
    stdout_digest: str
    stderr_digest: str


class ApprovalSource(Protocol):
    def fetch(self, request_id: str) -> tuple[dict[str, object], str]: ...


class GhApprovalSource:
    def __init__(self, repository: str) -> None:
        self.repository = repository

    def fetch(self, request_id: str) -> tuple[dict[str, object], str]:
        if _REQUEST_ID.fullmatch(request_id) is None:
            raise ApprovalExecutionError("INVALID_REQUEST_ID")
        path = f"approvals/self-improvement/{request_id}.json"
        commit = subprocess.run(
            (
                "gh",
                "api",
                f"repos/{self.repository}/commits",
                "--method",
                "GET",
                "-f",
                f"path={path}",
                "-f",
                "per_page=1",
                "--jq",
                ".[0].sha",
            ),
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            check=False,
        )
        if commit.returncode != 0 or not commit.stdout.strip():
            raise ApprovalExecutionError("GITHUB_APPROVAL_COMMIT_UNRESOLVED")
        source_commit_sha = commit.stdout.strip()
        completed = subprocess.run(
            (
                "gh",
                "api",
                f"repos/{self.repository}/contents/{path}",
                "--method",
                "GET",
                "-f",
                f"ref={source_commit_sha}",
                "-H",
                "Accept: application/vnd.github.raw+json",
            ),
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ApprovalExecutionError("GITHUB_APPROVAL_FETCH_FAILED")
        try:
            document = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ApprovalExecutionError("GITHUB_APPROVAL_INVALID_JSON") from exc
        return document, source_commit_sha


def parse_approval_receipt(
    document: dict[str, object], *, source_commit_sha: str
) -> OwnerApprovalReceipt:
    if document.get("schema_version") != "apf.owner-approval-receipt/1.0":
        raise ApprovalExecutionError("APPROVAL_SCHEMA_INVALID")
    if document.get("state") != "OWNER_APPROVED":
        raise ApprovalExecutionError("OWNER_APPROVED_STATE_REQUIRED")
    request_id = document.get("request_id")
    scope_digest = document.get("scope_digest")
    approver = document.get("approver")
    approved_at = document.get("approved_at")
    if not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None:
        raise ApprovalExecutionError("INVALID_REQUEST_ID")
    if not isinstance(scope_digest, str) or _DIGEST.fullmatch(scope_digest) is None:
        raise ApprovalExecutionError("INVALID_SCOPE_DIGEST")
    if not isinstance(approver, str) or not approver.strip():
        raise ApprovalExecutionError("APPROVER_REQUIRED")
    if not isinstance(approved_at, str):
        raise ApprovalExecutionError("APPROVED_AT_REQUIRED")
    try:
        parsed_time = datetime.fromisoformat(approved_at)
    except ValueError as exc:
        raise ApprovalExecutionError("APPROVED_AT_INVALID") from exc
    if parsed_time.tzinfo is None:
        raise ApprovalExecutionError("APPROVED_AT_TIMEZONE_REQUIRED")
    if _GIT_OBJECT_ID.fullmatch(source_commit_sha) is None:
        raise ApprovalExecutionError("APPROVAL_SOURCE_COMMIT_INVALID")
    allowed_paths = _validated_paths(document.get("allowed_paths"))
    allowed_operations = _validated_strings(
        document.get("allowed_operations"), "ALLOWED_OPERATIONS_REQUIRED"
    )
    return OwnerApprovalReceipt(
        request_id=request_id,
        scope_digest=scope_digest,
        approver=approver.strip(),
        approved_at=approved_at,
        allowed_paths=allowed_paths,
        allowed_operations=allowed_operations,
        source_commit_sha=source_commit_sha,
    )


def record_approval(
    *,
    ledger_path: Path,
    receipt: OwnerApprovalReceipt,
    expected_request_id: str,
    expected_scope_digest: str,
) -> str:
    if receipt.request_id != expected_request_id or receipt.scope_digest != expected_scope_digest:
        raise ApprovalExecutionError("APPROVAL_SCOPE_BINDING_MISMATCH")
    entries: list[dict[str, object]] = []
    if ledger_path.exists():
        document = json.loads(ledger_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.owner-approval-ledger/1.0":
            raise ApprovalExecutionError("APPROVAL_LEDGER_SCHEMA_INVALID")
        entries = list(document.get("entries") or [])
    entry = {**receipt.canonical_document(), "receipt_digest": receipt.digest()}
    for existing in entries:
        if existing.get("request_id") == receipt.request_id:
            if existing != entry:
                raise ApprovalExecutionError("APPROVAL_LEDGER_CONFLICT")
            return receipt.digest()
    entries.append(entry)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ledger_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"schema_version": "apf.owner-approval-ledger/1.0", "entries": entries},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(ledger_path)
    return receipt.digest()


def run_in_approved_worktree(
    *,
    repository_root: Path,
    worktrees_root: Path,
    receipt: OwnerApprovalReceipt,
    expected_scope_digest: str,
    base_sha: str,
    command: Sequence[str],
    cwd: str = ".",
) -> WorktreeRunResult:
    if receipt.scope_digest != expected_scope_digest:
        raise ApprovalExecutionError("RUNNER_SCOPE_DIGEST_MISMATCH")
    if "RUN_TESTS" not in receipt.allowed_operations:
        raise ApprovalExecutionError("RUN_TESTS_NOT_APPROVED")
    if _GIT_OBJECT_ID.fullmatch(base_sha) is None:
        raise ApprovalExecutionError("BASE_SHA_INVALID")
    if not command or Path(command[0]).name.lower() not in _ALLOWED_EXECUTABLES:
        raise ApprovalExecutionError("COMMAND_NOT_ALLOWLISTED")
    relative_cwd = _validated_relative_path(cwd, allow_root=True)
    if relative_cwd != "." and not any(
        relative_cwd == allowed or relative_cwd.startswith(allowed + "/")
        for allowed in receipt.allowed_paths
    ):
        raise ApprovalExecutionError("COMMAND_CWD_OUTSIDE_APPROVED_PATHS")
    worktree = worktrees_root.resolve() / receipt.request_id
    if worktree.exists():
        raise ApprovalExecutionError("WORKTREE_ALREADY_EXISTS")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git(repository_root, "cat-file", "-e", f"{base_sha}^{{commit}}")
    _git(repository_root, "worktree", "add", "--detach", str(worktree), base_sha)
    completed = subprocess.run(
        tuple(command),
        cwd=worktree / relative_cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env={"PATH": os.defpath, "PYTHONPATH": str(worktree / "src")},
    )
    return WorktreeRunResult(
        request_id=receipt.request_id,
        worktree_path=str(worktree),
        base_sha=base_sha,
        receipt_digest=receipt.digest(),
        command=tuple(command),
        returncode=completed.returncode,
        stdout_digest="sha256:" + sha256(completed.stdout.encode()).hexdigest(),
        stderr_digest="sha256:" + sha256(completed.stderr.encode()).hexdigest(),
    )


def _git(root: Path, *arguments: str) -> None:
    completed = subprocess.run(
        ("git", "-C", str(root.resolve()), *arguments), capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ApprovalExecutionError("GIT_WORKTREE_OPERATION_FAILED")


def _validated_strings(value: object, code: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ApprovalExecutionError(code)
    return tuple(value)


def _validated_paths(value: object) -> tuple[str, ...]:
    values = _validated_strings(value, "ALLOWED_PATHS_REQUIRED")
    return tuple(_validated_relative_path(item) for item in values)


def _validated_relative_path(value: str, *, allow_root: bool = False) -> str:
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        (normalized == "." and not allow_root)
        or not normalized
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
    ):
        raise ApprovalExecutionError("UNSAFE_APPROVED_PATH")
    return posix.as_posix()
