from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol
from uuid import UUID

from .development_orchestrator import (
    DevelopmentOrchestrator,
    TaskContract,
    TaskResult,
    TaskStatus,
    Worker,
)


@dataclass(frozen=True)
class WorkerExecution:
    result: TaskResult
    touched_paths: tuple[str, ...]


class WorkerExecutor(Protocol):
    def execute(self, task: TaskContract) -> WorkerExecution: ...


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
    ) -> None:
        self.orchestrator = orchestrator
        self.worker = worker
        self.executor = executor
        self.receipts = receipts

    def run_once(self) -> ExecutionReceipt | None:
        task = self.orchestrator.claim(self.worker)
        if task is None:
            return None
        try:
            execution = self.executor.execute(task)
            if not _within_scope(execution.touched_paths, task.allowed_paths):
                result = TaskResult((), ("SCOPE_CHECK_FAILED",), "FAIL")
                failure_code = "SCOPE_VIOLATION"
            else:
                result = execution.result
                failure_code = None if result.outcome == "PASS" else "EXECUTION_FAILED"
            completed = self.orchestrator.complete(task.task_id, task.lease_token, result)
            touched_paths = execution.touched_paths
        except (OSError, ValueError) as exc:
            failure_code = f"EXECUTOR_ERROR:{type(exc).__name__}"
            completed = self.orchestrator.complete(
                task.task_id,
                task.lease_token,
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


def _within_scope(touched_paths: tuple[str, ...], allowed_paths: tuple[str, ...]) -> bool:
    allowed = [PurePosixPath(value) for value in allowed_paths]
    for raw_path in touched_paths:
        path = PurePosixPath(raw_path)
        if path.is_absolute() or ".." in path.parts:
            return False
        if not any(path == root or root in path.parents for root in allowed):
            return False
    return True
