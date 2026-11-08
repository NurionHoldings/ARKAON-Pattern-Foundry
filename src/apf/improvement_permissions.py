"""One-use task capabilities issued by the trusted Eternian host, not a worker.

This controls dispatch, not OS isolation. A connected executor must additionally
confine filesystem/process/network access before it receives a task.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .development_orchestrator import HUMAN_ONLY, TaskContract
from .execution_sandbox import prepare_execution_sandbox

_PROTECTED_PATHS = (
    "src/apf/improvement_permissions.py",
    "src/apf/worker_runtime.py",
    "src/apf/execution_sandbox.py",
    "src/apf/development_orchestrator.py",
    "src/apf/console.py",
    "src/apf/approval_tokens.py",
    "src/apf/self_improvement_execution.py",
    "scripts/build_static.py",
    "netlify.toml",
    "pyproject.toml",
    "package.json",
)


class ImprovementPermissionDenied(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ImprovementGrant:
    grant_id: str
    owner_instruction_ref: str
    worker_id: str
    task_digest: str
    worktree_root: str
    expires_at: datetime
    issuer: str = "ETERNIAN"


def _task_digest(task: TaskContract) -> str:
    document = {
        "task_id": str(task.task_id),
        "kind": task.kind.value,
        "intent": task.intent_fingerprint,
        "objective": task.objective,
        "paths": task.allowed_paths,
        "operations": task.requested_operations,
        "artifacts": task.expected_artifacts,
        "dependencies": [str(value) for value in task.dependencies],
        "approval_ref": task.approval_ref,
    }
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()


class ImprovementGrantAuthority:
    """Host-owned registry. Do not pass this issuer object to untrusted executors.

    The host must establish owner authorization before constructing it. The
    instruction reference is an audit binding, not proof of authentication.
    Grants are kept in memory, expire, can be revoked, and cannot be replayed.
    """

    def __init__(
        self,
        *,
        worktree_root: str | Path,
        owner_instruction_ref: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not owner_instruction_ref.strip():
            raise ImprovementPermissionDenied("OWNER_INSTRUCTION_REQUIRED")
        self.root = str(Path(worktree_root).resolve())
        self.owner_instruction_ref = owner_instruction_ref
        self.clock = clock or (lambda: datetime.now(UTC))
        self._grants: dict[str, ImprovementGrant] = {}
        self._lock = RLock()

    def issue(
        self, task: TaskContract, *, worker_id: str, lifetime: timedelta = timedelta(minutes=15)
    ) -> tuple[str, ImprovementGrant]:
        if not worker_id.strip() or not timedelta(0) < lifetime <= timedelta(hours=1):
            raise ImprovementPermissionDenied("INVALID_DELEGATION_LIMIT")
        if task.kind in HUMAN_ONLY:
            raise ImprovementPermissionDenied("HUMAN_AUTHORITY_NOT_DELEGABLE")
        if not task.requested_operations:
            raise ImprovementPermissionDenied("EXPLICIT_OPERATIONS_REQUIRED")
        # Reuse the existing denylist for network, secrets and unknown operations.
        policy, _ = prepare_execution_sandbox(task, worktree_root=self.root)
        may_write = bool(set(task.requested_operations) & {"WRITE_WORKTREE", "GENERATE_ARTIFACT"})
        for raw in policy.allowed_paths:
            parts = tuple(part.casefold() for part in Path(raw).parts)
            if any(
                part in {".git", ".ssh", ".aws", "secrets", "private", "customer-data"}
                or part.startswith(".env")
                for part in parts
            ):
                raise ImprovementPermissionDenied("SENSITIVE_SCOPE_NOT_DELEGABLE")
            scope = Path(raw.casefold())
            if may_write and (
                any(part in {".github", "approvals", "config"} for part in parts)
                or any(
                    scope == Path(path) or scope in Path(path).parents for path in _PROTECTED_PATHS
                )
            ):
                raise ImprovementPermissionDenied("CONTROL_PLANE_SCOPE_NOT_DELEGABLE")
        now = self.clock()
        if now.tzinfo is None:
            raise ImprovementPermissionDenied("TIMEZONE_REQUIRED")
        grant = ImprovementGrant(
            uuid4().hex,
            self.owner_instruction_ref,
            worker_id,
            _task_digest(task),
            self.root,
            now + lifetime,
        )
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._grants[token] = grant
        return token, grant

    def revoke(self, token: str) -> None:
        with self._lock:
            self._grants.pop(token, None)

    def consume(
        self, token: str | None, task: TaskContract, *, worker_id: str, worktree_root: str | Path
    ) -> ImprovementGrant:
        now = self.clock()
        if now.tzinfo is None:
            raise ImprovementPermissionDenied("TIMEZONE_REQUIRED")
        with self._lock:
            grant = self._grants.get(token or "")
            if grant is None:
                raise ImprovementPermissionDenied("DELEGATION_MISSING_REVOKED_OR_USED")
            if now >= grant.expires_at:
                self._grants.pop(token, None)
                raise ImprovementPermissionDenied("DELEGATION_EXPIRED")
            if (
                grant.worker_id != worker_id
                or grant.task_digest != _task_digest(task)
                or grant.worktree_root != str(Path(worktree_root).resolve())
            ):
                raise ImprovementPermissionDenied("DELEGATION_BINDING_MISMATCH")
            del self._grants[token]
            return grant
