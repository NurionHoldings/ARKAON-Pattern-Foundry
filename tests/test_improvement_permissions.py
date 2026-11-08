from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from apf.development_orchestrator import (
    DevelopmentOrchestrator,
    TaskKind,
    TaskStatus,
    Worker,
    task_contract,
)
from apf.improvement_permissions import ImprovementGrantAuthority, ImprovementPermissionDenied
from apf.worker_runtime import ArkaonWorkerRuntime, MemoryReceiptSink

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def task(**changes):
    values = {
        "intent_fingerprint": "a" * 64,
        "objective": "improve a requested feature",
        "allowed_paths": ("services/feature.js",),
        "expected_artifacts": ("feature.patch",),
        "requested_operations": ("READ_WORKTREE", "WRITE_WORKTREE", "RUN_TESTS"),
    }
    values.update(changes)
    return task_contract(TaskKind.BUILD, **values)


def authority(root, clock=lambda: NOW):
    return ImprovementGrantAuthority(
        worktree_root=root, owner_instruction_ref="owner-request", clock=clock
    )


def test_single_use_grant_is_task_worker_root_bound_and_does_not_leak_token(tmp_path):
    host = authority(tmp_path)
    work = task()
    token, grant = host.issue(work, worker_id="arkaon-builder")
    assert token not in repr(grant)
    for change in (
        {"objective": "expand scope"},
        {"allowed_paths": ("services/other.js",)},
        {"requested_operations": ("NETWORK",)},
        {"expected_artifacts": ("other",)},
    ):
        with pytest.raises(ImprovementPermissionDenied, match="BINDING_MISMATCH"):
            host.consume(
                token, replace(work, **change), worker_id="arkaon-builder", worktree_root=tmp_path
            )
    for worker, root in [("other-worker", tmp_path), ("arkaon-builder", tmp_path / "other")]:
        with pytest.raises(ImprovementPermissionDenied, match="BINDING_MISMATCH"):
            host.consume(token, work, worker_id=worker, worktree_root=root)
    assert host.consume(token, work, worker_id="arkaon-builder", worktree_root=tmp_path) == grant
    with pytest.raises(ImprovementPermissionDenied, match="MISSING_REVOKED_OR_USED"):
        host.consume(token, work, worker_id="arkaon-builder", worktree_root=tmp_path)


def test_expiry_and_revocation(tmp_path):
    clock = [NOW]
    host = authority(tmp_path, lambda: clock[0])
    work = task()
    token, _ = host.issue(work, worker_id="arkaon", lifetime=timedelta(seconds=5))
    clock[0] += timedelta(seconds=5)
    with pytest.raises(ImprovementPermissionDenied, match="EXPIRED"):
        host.consume(token, work, worker_id="arkaon", worktree_root=tmp_path)
    token, _ = host.issue(work, worker_id="arkaon")
    host.revoke(token)
    with pytest.raises(ImprovementPermissionDenied, match="MISSING_REVOKED_OR_USED"):
        host.consume(token, work, worker_id="arkaon", worktree_root=tmp_path)


@pytest.mark.parametrize(
    "scope",
    [
        "src/",
        "src/apf/improvement_permissions.py",
        ".github/workflows/release.yml",
        ".ENV",
        "config/policy.json",
        "approvals/receipt.json",
        "secrets/key",
        "netlify.toml",
    ],
)
def test_delegation_cannot_modify_its_own_controls(tmp_path, scope):
    with pytest.raises(ImprovementPermissionDenied, match="SCOPE_NOT_DELEGABLE"):
        authority(tmp_path).issue(task(allowed_paths=(scope,)), worker_id="arkaon")


@pytest.mark.parametrize("operation", ["DEPLOY", "MERGE", "PAY", "READ_SECRET", "NETWORK"])
def test_operational_or_secret_privileges_cannot_be_granted(tmp_path, operation):
    with pytest.raises(ValueError):
        authority(tmp_path).issue(task(requested_operations=(operation,)), worker_id="arkaon")


def test_topics_are_not_restricted_by_permission_scope(tmp_path):
    host = authority(tmp_path)
    for topic in ["CSS animation", "천문학", "새로운 데이터 분석 구현법"]:
        work = task(objective=topic, requested_operations=("READ_WORKTREE",))
        token, _ = host.issue(work, worker_id="arkaon")
        assert host.consume(token, work, worker_id="arkaon", worktree_root=tmp_path)


def test_absent_grant_stops_dispatch_before_executor_runs(tmp_path):
    class NeverExecute:
        def execute(self, *args, **kwargs):
            raise AssertionError("unauthorized executor was reached")

    orchestrator = DevelopmentOrchestrator()
    work = orchestrator.submit(task())
    runtime = ArkaonWorkerRuntime(
        orchestrator,
        Worker("arkaon", frozenset({TaskKind.BUILD})),
        NeverExecute(),
        MemoryReceiptSink(),
        worktree_root=tmp_path,
        assigned_task_id=work.task_id,
    )
    receipt = runtime.run_once()
    assert receipt.status == TaskStatus.FAILED
    assert receipt.failure_code == "DELEGATION_REQUIRED"


def test_explicit_operations_and_short_lifetime_are_required(tmp_path):
    host = authority(tmp_path)
    with pytest.raises(ImprovementPermissionDenied, match="EXPLICIT_OPERATIONS_REQUIRED"):
        host.issue(task(requested_operations=()), worker_id="arkaon")
    with pytest.raises(ImprovementPermissionDenied, match="INVALID_DELEGATION_LIMIT"):
        host.issue(task(), worker_id="arkaon", lifetime=timedelta(days=1))


def test_reading_implementation_controls_is_allowed_without_authorizing_changes(tmp_path):
    host = authority(tmp_path)
    work = task(allowed_paths=('src/apf/', 'config/'),
                requested_operations=('READ_WORKTREE',))
    token, _ = host.issue(work, worker_id='arkaon-researcher')
    assert host.consume(token, work, worker_id='arkaon-researcher', worktree_root=tmp_path)


def test_two_workers_cannot_consume_the_same_grant(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    host = authority(tmp_path)
    work = task()
    token, _ = host.issue(work, worker_id='arkaon')

    def consume_once(_):
        try:
            host.consume(token, work, worker_id='arkaon', worktree_root=tmp_path)
            return True
        except ImprovementPermissionDenied:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume_once, range(2))) == [False, True]
