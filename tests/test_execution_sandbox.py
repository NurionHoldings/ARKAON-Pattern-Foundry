from dataclasses import replace

import pytest

from apf.development_orchestrator import TaskKind, task_contract
from apf.execution_sandbox import (
    SandboxPolicyDenied,
    prepare_execution_sandbox,
    verify_attestation,
)


def contract(*, allowed_paths=("src/apf",), requested_operations=()):
    return task_contract(
        TaskKind.BUILD,
        intent_fingerprint="a" * 64,
        objective="isolated build",
        allowed_paths=allowed_paths,
        expected_artifacts=("implementation.patch",),
        requested_operations=requested_operations,
    )


def test_builds_fail_closed_policy_and_verifiable_attestation(tmp_path):
    policy, attestation = prepare_execution_sandbox(
        contract(requested_operations=("WRITE_WORKTREE", "RUN_TESTS")),
        worktree_root=tmp_path,
    )

    assert policy.allowed_paths == ("src/apf",)
    assert policy.network_enabled is False
    assert policy.injected_secrets == ()
    assert attestation.network_blocked is True
    assert attestation.secrets_injected is False
    assert verify_attestation(policy, attestation)


@pytest.mark.parametrize(
    "unsafe_path",
    ("/etc/passwd", "../outside", "src/../../outside", r"C:\\Windows\\System32"),
)
def test_rejects_absolute_parent_and_drive_paths(tmp_path, unsafe_path):
    with pytest.raises(SandboxPolicyDenied, match="UNSAFE_ALLOWED_PATH"):
        prepare_execution_sandbox(contract(allowed_paths=(unsafe_path,)), worktree_root=tmp_path)


@pytest.mark.parametrize(
    ("operation", "reason"),
    (
        ("NETWORK_ACCESS", "NETWORK_ACCESS_DENIED"),
        ("INJECT_SECRET", "SECRET_INJECTION_DENIED"),
        ("EXECUTE_ARBITRARY_HOST_COMMAND", "UNKNOWN_OPERATION_DENIED"),
    ),
)
def test_denies_network_secrets_and_unknown_operations(tmp_path, operation, reason):
    with pytest.raises(SandboxPolicyDenied, match=reason):
        prepare_execution_sandbox(
            contract(requested_operations=(operation,)),
            worktree_root=tmp_path,
        )


def test_attestation_detects_policy_tampering(tmp_path):
    policy, attestation = prepare_execution_sandbox(contract(), worktree_root=tmp_path)
    tampered = replace(policy, network_enabled=True)

    assert not verify_attestation(tampered, attestation)
