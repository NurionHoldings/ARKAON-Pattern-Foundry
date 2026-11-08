from apf.development_orchestrator import (
    DevelopmentOrchestrator,
    TaskKind,
    TaskResult,
    TaskStatus,
    Worker,
    task_contract,
)
from apf.improvement_permissions import ImprovementGrantAuthority
from apf.worker_runtime import (
    ArkaonWorkerPool,
    ArkaonWorkerRuntime,
    MemoryReceiptSink,
    WorkerExecution,
)


class Executor:
    def __init__(self, execution=None, error=None):
        self.execution = execution
        self.error = error

    def execute(self, task, *, sandbox_policy, attestation):
        if self.error:
            raise self.error
        return self.execution


def runtime(executor):
    orchestrator = DevelopmentOrchestrator()
    task = orchestrator.submit(
        task_contract(
            TaskKind.BUILD,
            intent_fingerprint="a" * 64,
            objective="build feature",
            allowed_paths=("src/feature.py", "tests/test_feature.py"),
            requested_operations=("WRITE_WORKTREE", "RUN_TESTS"),
            expected_artifacts=("implementation.patch",),
        )
    )
    receipts = MemoryReceiptSink()
    authority = ImprovementGrantAuthority(
        worktree_root="/tmp/arkaon-worktree", owner_instruction_ref="test-owner-request",
    )
    token, _ = authority.issue(task, worker_id="arkaon-builder")
    worker_runtime = ArkaonWorkerRuntime(
        orchestrator,
        Worker("arkaon-builder", frozenset({TaskKind.BUILD})),
        executor,
        receipts,
        worktree_root="/tmp/arkaon-worktree",
        grant_authority=authority, grant_token=token, assigned_task_id=task.task_id,
    )
    return task, receipts, worker_runtime


def test_worker_executes_claimed_task_and_records_traceable_receipt():
    task, receipts, worker = runtime(
        Executor(
            WorkerExecution(
                TaskResult(("implementation.patch",), ("pytest", "ruff"), "PASS"),
                ("src/feature.py", "tests/test_feature.py"),
            )
        )
    )
    receipt = worker.run_once()
    assert receipt.task_id == task.task_id
    assert receipt.intent_fingerprint == "a" * 64
    assert receipt.status == TaskStatus.SUCCEEDED
    assert receipts.receipts == [receipt]


def test_out_of_scope_write_fails_closed():
    _, _, worker = runtime(
        Executor(
            WorkerExecution(
                TaskResult(("implementation.patch",), ("pytest",), "PASS"),
                (".github/workflows/release.yml",),
            )
        )
    )
    receipt = worker.run_once()
    assert receipt.status == TaskStatus.FAILED
    assert receipt.failure_code == "SCOPE_VIOLATION"


def test_executor_failure_is_sanitized_and_does_not_escape_runtime():
    _, _, worker = runtime(Executor(error=OSError("secret upstream detail")))
    receipt = worker.run_once()
    assert receipt.status == TaskStatus.FAILED
    assert receipt.failure_code == "EXECUTOR_ERROR:OSError"
    assert "secret" not in receipt.failure_code


def test_worker_without_eligible_task_returns_idle():
    orchestrator = DevelopmentOrchestrator()
    worker = ArkaonWorkerRuntime(
        orchestrator,
        Worker("arkaon-verifier", frozenset({TaskKind.VERIFY})),
        Executor(),
        MemoryReceiptSink(),
        worktree_root="/tmp/arkaon-worktree",
    )
    assert worker.run_once() is None


def test_worker_pool_claims_independent_tasks_without_duplicate_execution():
    orchestrator = DevelopmentOrchestrator()
    tasks = [
        orchestrator.submit(
            task_contract(
                TaskKind.BUILD,
                intent_fingerprint="a" * 64,
                objective=f"build-{index}",
                allowed_paths=("src/feature.py",),
                requested_operations=("WRITE_WORKTREE", "RUN_TESTS"),
                expected_artifacts=("implementation.patch",),
            )
        )
        for index in range(2)
    ]
    receipts = MemoryReceiptSink()
    execution = WorkerExecution(
        TaskResult(("implementation.patch",), ("pytest",), "PASS"),
        ("src/feature.py",),
    )
    authority = ImprovementGrantAuthority(
        worktree_root="/tmp/arkaon-worktree", owner_instruction_ref="test-owner-request",
    )
    workers = []
    for index, task in enumerate(tasks):
        worker_id = f"arkaon-builder-{index}"
        token, _ = authority.issue(task, worker_id=worker_id)
        workers.append(ArkaonWorkerRuntime(
            orchestrator, Worker(worker_id, frozenset({TaskKind.BUILD})),
            Executor(execution), receipts, worktree_root="/tmp/arkaon-worktree",
            grant_authority=authority, grant_token=token, assigned_task_id=task.task_id,
        ))
    completed = ArkaonWorkerPool(tuple(workers)).run_available()
    assert len(completed) == 2
    assert {receipt.task_id for receipt in completed} == {task.task_id for task in tasks}
