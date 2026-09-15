from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from .development_orchestrator import (
    DevelopmentOrchestrator,
    TaskContract,
    TaskResult,
    TaskStatus,
    Worker,
)
from .execution_sandbox import prepare_execution_sandbox, verify_attestation


@dataclass(frozen=True)
class WorkerExecution:
    result: TaskResult
    touched_paths: tuple[str, ...]


class WorkerExecutor(Protocol):
    def execute(self, task: TaskContract, *, sandbox_policy, attestation) -> WorkerExecution: ...


@dataclass(frozen=True)
class ExecutionReceipt:
    task_id: UUID
    worker_id: str
    intent_fingerprint: str
    status: TaskStatus
    touched_paths: tuple[str, ...]
    checks: tuple[str, ...]
    failure_code: str | None = None


class ReceiptSink(Protocol):
    def record(self, receipt: ExecutionReceipt) -> None: ...


class MemoryReceiptSink:
    def __init__(self) -> None:
        self.receipts: list[ExecutionReceipt] = []

    def record(self, receipt: ExecutionReceipt) -> None:
        self.receipts.append(receipt)


class ArkaonWorkerRuntime:
    def __init__(
        self,
        orchestrator: DevelopmentOrchestrator,
        worker: Worker,
        executor: WorkerExecutor,
        receipts: ReceiptSink,
        *,
        worktree_root: str | Path,
    ) -> None:
        self.orchestrator = orchestrator
        self.worker = worker
        self.executor = executor
        self.receipts = receipts
        self.worktree_root = Path(worktree_root)

    def run_once(self) -> ExecutionReceipt | None:
        task = self.orchestrator.claim(self.worker)
        if task is None:
            return None
        try:
            policy, attestation = prepare_execution_sandbox(
                task, worktree_root=self.worktree_root
            )
            if not verify_attestation(policy, attestation):
                raise ValueError("INVALID_SANDBOX_ATTESTATION")
            execution = self.executor.execute(
                task,
                sandbox_policy=policy,
                attestation=attestation,
            )
            if not _within_scope(execution.touched_paths, task.allowed_paths):
                result = TaskResult((), ("SCOPE_CHECK_FAILED",), "FAIL")
                failure_code = "SCOPE_VIOLATION"
            else:
                result = execution.result
                failure_code = None if result.outcome == "PASS" else "EXECUTION_FAILED"
            completed = self.orchestrator.complete(
                task.task_id,
                task.lease_token,
                self.worker.worker_id,
                result,
            )
            touched_paths = execution.touched_paths
        except (OSError, ValueError) as exc:
            failure_code = f"EXECUTOR_ERROR:{type(exc).__name__}"
            completed = self.orchestrator.complete(
                task.task_id,
                task.lease_token,
                self.worker.worker_id,
                TaskResult((), (failure_code,), "FAIL"),
            )
            touched_paths = ()
            result = TaskResult((), (failure_code,), "FAIL")
        receipt = ExecutionReceipt(
            task_id=task.task_id,
            worker_id=self.worker.worker_id,
            intent_fingerprint=task.intent_fingerprint,
            status=completed.status,
            touched_paths=touched_paths,
            checks=result.checks,
            failure_code=failure_code,
        )
        self.receipts.record(receipt)
        return receipt


class ArkaonWorkerPool:
    def __init__(self, workers: tuple[ArkaonWorkerRuntime, ...]) -> None:
        if not workers:
            raise ValueError("at least one worker is required")
        self.workers = workers

    def run_available(self) -> tuple[ExecutionReceipt, ...]:
        with ThreadPoolExecutor(max_workers=len(self.workers), thread_name_prefix="arkaon") as pool:
            receipts = tuple(pool.map(lambda worker: worker.run_once(), self.workers))
        return tuple(receipt for receipt in receipts if receipt is not None)


def _within_scope(touched_paths: tuple[str, ...], allowed_paths: tuple[str, ...]) -> bool:
    allowed = [PurePosixPath(value) for value in allowed_paths]
    for raw_path in touched_paths:
        path = PurePosixPath(raw_path)
        if path.is_absolute() or ".." in path.parts:
            return False
        if not any(path == root or root in path.parents for root in allowed):
            return False
    return True
