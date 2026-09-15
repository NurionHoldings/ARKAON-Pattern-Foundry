from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from threading import RLock
from uuid import UUID, uuid4


class TaskKind(StrEnum):
    RESEARCH = "RESEARCH"
    ANALYZE = "ANALYZE"
    ARCHITECT = "ARCHITECT"
    BUILD = "BUILD"
    TEST = "TEST"
    VERIFY = "VERIFY"
    AUDIT = "AUDIT"
    REPORT = "REPORT"
    REGISTER_EVIDENCE = "REGISTER_EVIDENCE"
    REQUEST_ACTION = "REQUEST_ACTION"
    MUTATE_INTENT = "MUTATE_INTENT"
    PROMOTE_OWNED_ASSET = "PROMOTE_OWNED_ASSET"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    BLOCKED_HUMAN_APPROVAL = "BLOCKED_HUMAN_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


HUMAN_ONLY = frozenset({TaskKind.MUTATE_INTENT, TaskKind.PROMOTE_OWNED_ASSET})
PROHIBITED_OPERATIONS = frozenset(
    {
        "READ_SECRET_VALUE",
        "BYPASS_ACCESS_CONTROL",
        "DELETE_AUDIT",
        "SELF_ESCALATE_AUTHORITY",
        "COPY_RESTRICTED_SOURCE",
    }
)


@dataclass(frozen=True)
class TaskContract:
    task_id: UUID
    kind: TaskKind
    intent_fingerprint: str
    objective: str
    allowed_paths: tuple[str, ...]
    expected_artifacts: tuple[str, ...]
    dependencies: tuple[UUID, ...] = ()
    requested_operations: tuple[str, ...] = ()
    approval_ref: str | None = None
    status: TaskStatus = TaskStatus.QUEUED
    lease_token: UUID | None = None
    produced_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Worker:
    worker_id: str
    capabilities: frozenset[TaskKind]


@dataclass(frozen=True)
class TaskResult:
    artifacts: tuple[str, ...]
    checks: tuple[str, ...]
    outcome: str


@dataclass(frozen=True)
class DelegationPlan:
    goal: str
    tasks: tuple[TaskContract, ...]

    @property
    def final_task_id(self) -> UUID:
        return self.tasks[-1].task_id


class OrchestrationDenied(ValueError):
    pass


class DevelopmentOrchestrator:
    def __init__(self) -> None:
        self._tasks: dict[UUID, TaskContract] = {}
        self._lock = RLock()

    def submit(self, contract: TaskContract) -> TaskContract:
        forbidden = PROHIBITED_OPERATIONS & set(contract.requested_operations)
        if forbidden:
            raise OrchestrationDenied("PROHIBITED_OPERATION:" + ",".join(sorted(forbidden)))
        if not contract.intent_fingerprint or not contract.allowed_paths:
            raise OrchestrationDenied("INTENT_AND_SCOPE_REQUIRED")
        if contract.kind in HUMAN_ONLY and not contract.approval_ref:
            contract = replace(contract, status=TaskStatus.BLOCKED_HUMAN_APPROVAL)
        with self._lock:
            self._tasks[contract.task_id] = contract
        return contract

    def claim(self, worker: Worker) -> TaskContract | None:
        if worker.capabilities & HUMAN_ONLY:
            raise OrchestrationDenied("HUMAN_ONLY_CAPABILITY_NOT_DELEGABLE")
        with self._lock:
            completed = {
                task_id for task_id, task in self._tasks.items() if task.status == TaskStatus.SUCCEEDED
            }
            eligible = sorted(
                (
                    task
                    for task in self._tasks.values()
                    if task.status == TaskStatus.QUEUED
                    and task.kind not in HUMAN_ONLY
                    and task.kind in worker.capabilities
                    and set(task.dependencies) <= completed
                ),
                key=lambda task: str(task.task_id),
            )
            if not eligible:
                return None
            claimed = replace(eligible[0], status=TaskStatus.RUNNING, lease_token=uuid4())
            self._tasks[claimed.task_id] = claimed
            return claimed

    def complete(self, task_id: UUID, lease_token: UUID, result: TaskResult) -> TaskContract:
        with self._lock:
            task = self._tasks[task_id]
            if task.status != TaskStatus.RUNNING or task.lease_token != lease_token:
                raise OrchestrationDenied("INVALID_OR_STALE_LEASE")
            missing = set(task.expected_artifacts) - set(result.artifacts)
            if missing or result.outcome != "PASS" or not result.checks:
                failed = replace(task, status=TaskStatus.FAILED, produced_artifacts=result.artifacts)
                self._tasks[task_id] = failed
                return failed
            completed = replace(
                task,
                status=TaskStatus.SUCCEEDED,
                produced_artifacts=result.artifacts,
                lease_token=None,
            )
            self._tasks[task_id] = completed
            return completed

    def get(self, task_id: UUID) -> TaskContract:
        with self._lock:
            return self._tasks[task_id]

    def snapshot(self) -> tuple[TaskContract, ...]:
        with self._lock:
            return tuple(self._tasks.values())

    def restore(self, contracts: tuple[TaskContract, ...]) -> None:
        with self._lock:
            self._tasks = {contract.task_id: contract for contract in contracts}


def task_contract(
    kind: TaskKind,
    *,
    intent_fingerprint: str,
    objective: str,
    allowed_paths: tuple[str, ...],
    expected_artifacts: tuple[str, ...],
    dependencies: tuple[UUID, ...] = (),
    requested_operations: tuple[str, ...] = (),
    approval_ref: str | None = None,
) -> TaskContract:
    return TaskContract(
        task_id=uuid4(),
        kind=kind,
        intent_fingerprint=intent_fingerprint,
        objective=objective,
        allowed_paths=allowed_paths,
        expected_artifacts=expected_artifacts,
        dependencies=dependencies,
        requested_operations=requested_operations,
        approval_ref=approval_ref,
    )


def build_delegation_plan(
    goal: str,
    *,
    intent_fingerprint: str,
    allowed_paths: tuple[str, ...],
) -> DelegationPlan:
    if not goal.strip():
        raise OrchestrationDenied("GOAL_REQUIRED")
    stages = (
        (TaskKind.RESEARCH, "precedents.json"),
        (TaskKind.ANALYZE, "principles.json"),
        (TaskKind.ARCHITECT, "architecture.md"),
        (TaskKind.BUILD, "implementation.patch"),
        (TaskKind.TEST, "test-results.json"),
        (TaskKind.VERIFY, "verification.json"),
        (TaskKind.AUDIT, "audit.json"),
        (TaskKind.REGISTER_EVIDENCE, "evidence-registration.json"),
        (TaskKind.REPORT, "completion-report.md"),
    )
    tasks: list[TaskContract] = []
    dependency: tuple[UUID, ...] = ()
    for kind, artifact in stages:
        task = task_contract(
            kind,
            intent_fingerprint=intent_fingerprint,
            objective=f"{goal} :: {kind.value}",
            allowed_paths=allowed_paths,
            expected_artifacts=(artifact,),
            dependencies=dependency,
        )
        tasks.append(task)
        dependency = (task.task_id,)
    return DelegationPlan(goal=goal, tasks=tuple(tasks))


def submit_plan(orchestrator: DevelopmentOrchestrator, plan: DelegationPlan) -> None:
    for task in plan.tasks:
        orchestrator.submit(task)
