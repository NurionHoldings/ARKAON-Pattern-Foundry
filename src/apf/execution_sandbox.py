from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath

from .development_orchestrator import TaskContract

SAFE_OPERATIONS = frozenset(
    {
        "READ_WORKTREE",
        "WRITE_WORKTREE",
        "RUN_TESTS",
        "RUN_LINTER",
        "GENERATE_ARTIFACT",
    }
)
NETWORK_OPERATIONS = frozenset({"NETWORK", "NETWORK_ACCESS", "HTTP_REQUEST"})
SECRET_OPERATIONS = frozenset({"READ_SECRET", "READ_SECRET_VALUE", "INJECT_SECRET"})


class SandboxPolicyDenied(ValueError):
    """Raised before execution when a task cannot be safely isolated."""


@dataclass(frozen=True)
class ExecutionSandboxPolicy:
    task_id: str
    worktree_root: str
    allowed_paths: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    network_enabled: bool = False
    injected_secrets: tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxAttestation:
    task_id: str
    intent_fingerprint: str
    policy_digest: str
    network_blocked: bool
    secrets_injected: bool
    paths_confined: bool


def prepare_execution_sandbox(
    contract: TaskContract,
    *,
    worktree_root: str | Path,
) -> tuple[ExecutionSandboxPolicy, SandboxAttestation]:
    """Validate and attest an execution policy without running the task."""
    root = Path(worktree_root).resolve()
    if not root.is_absolute():  # pragma: no cover - resolve is absolute on supported platforms
        raise SandboxPolicyDenied("WORKTREE_ROOT_MUST_BE_ABSOLUTE")

    confined_paths = tuple(_confine_path(raw_path, root) for raw_path in contract.allowed_paths)
    operations = tuple(sorted(set(contract.requested_operations)))
    requested = set(operations)
    if requested & NETWORK_OPERATIONS:
        raise SandboxPolicyDenied("NETWORK_ACCESS_DENIED")
    if requested & SECRET_OPERATIONS:
        raise SandboxPolicyDenied("SECRET_INJECTION_DENIED")
    unknown = requested - SAFE_OPERATIONS
    if unknown:
        raise SandboxPolicyDenied("UNKNOWN_OPERATION_DENIED:" + ",".join(sorted(unknown)))

    policy = ExecutionSandboxPolicy(
        task_id=str(contract.task_id),
        worktree_root=str(root),
        allowed_paths=confined_paths,
        allowed_operations=operations,
    )
    attestation = SandboxAttestation(
        task_id=str(contract.task_id),
        intent_fingerprint=contract.intent_fingerprint,
        policy_digest=_policy_digest(policy, contract.intent_fingerprint),
        network_blocked=True,
        secrets_injected=False,
        paths_confined=True,
    )
    return policy, attestation


def verify_attestation(
    policy: ExecutionSandboxPolicy,
    attestation: SandboxAttestation,
) -> bool:
    return (
        attestation.task_id == policy.task_id
        and attestation.network_blocked
        and not attestation.secrets_injected
        and attestation.paths_confined
        and attestation.policy_digest
        == _policy_digest(policy, attestation.intent_fingerprint)
    )


def _confine_path(raw_path: str, root: Path) -> str:
    normalized = raw_path.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(raw_path)
    if (
        not normalized
        or normalized == "."
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in posix_path.parts
    ):
        raise SandboxPolicyDenied("UNSAFE_ALLOWED_PATH:" + raw_path)
    candidate = (root / Path(*posix_path.parts)).resolve()
    if candidate == root or root not in candidate.parents:
        raise SandboxPolicyDenied("PATH_OUTSIDE_WORKTREE:" + raw_path)
    return candidate.relative_to(root).as_posix()


def _policy_digest(policy: ExecutionSandboxPolicy, intent_fingerprint: str) -> str:
    payload = {
        "allowed_operations": policy.allowed_operations,
        "allowed_paths": policy.allowed_paths,
        "injected_secrets": policy.injected_secrets,
        "intent_fingerprint": intent_fingerprint,
        "network_enabled": policy.network_enabled,
        "task_id": policy.task_id,
        "worktree_root": policy.worktree_root,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()
