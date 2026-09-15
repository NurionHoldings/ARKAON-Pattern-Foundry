from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from time import monotonic_ns
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from .benchmark_campaign import CampaignPhase, EvidenceBenchmarkCampaign, TrialEvidence
from .development_orchestrator import (
    DevelopmentOrchestrator,
    TaskContract,
    TaskKind,
    TaskResult,
    TaskStatus,
    Worker,
)
from .learning_safety import LearningSafetyViolation, scan_learning_text
from .role_benchmark import BenchmarkReport, BenchmarkRole, BenchmarkThresholds
from .worker_runtime import (
    ArkaonWorkerRuntime,
    ExecutionReceipt,
    MemoryReceiptSink,
    WorkerExecution,
)

SYNTHETIC_INTENT = hashlib.sha256(
    b"APF-027: safe deterministic synthetic development campaign v1"
).hexdigest()
SAFE_ROOT = PurePosixPath("synthetic")
_GOVERNED_MARKERS = ("intent mutation", "asset promotion")


class ObservationKind(StrEnum):
    WORK = "WORK"
    REWORK = "REWORK"
    ETHERNIAN_INTERVENTION = "ETHERNIAN_INTERVENTION"
    INTENT_CHECK = "INTENT_CHECK"


@dataclass(frozen=True)
class SyntheticScenario:
    scenario_id: str
    role: BenchmarkRole
    objective: str
    input_items: tuple[str, ...]
    expected_artifact: str
    required_intent_checks: tuple[str, ...]

    def __post_init__(self) -> None:
        payload = " ".join((self.objective, *self.input_items)).casefold()
        if not self.scenario_id.strip() or not self.input_items:
            raise ValueError("SYNTHETIC_SCENARIO_CONTENT_REQUIRED")
        violations = {
            code
            for value in (self.objective, *self.input_items)
            for code in scan_learning_text(value)
        }
        if violations:
            raise LearningSafetyViolation(tuple(sorted(violations)))
        if any(marker in payload for marker in _GOVERNED_MARKERS):
            raise ValueError("GOVERNED_SYNTHETIC_OPERATION")
        path = PurePosixPath(self.expected_artifact)
        if path.is_absolute() or ".." in path.parts or SAFE_ROOT not in path.parents:
            raise ValueError("SYNTHETIC_ARTIFACT_SCOPE_REQUIRED")
        if not self.required_intent_checks:
            raise ValueError("INTENT_CHECKS_REQUIRED")


@dataclass(frozen=True)
class Observation:
    kind: ObservationKind
    detail: str
    elapsed_ns: int


class NanoClock(Protocol):
    def __call__(self) -> int: ...


class ObservationLog:
    def __init__(self, clock: NanoClock = monotonic_ns) -> None:
        self._clock = clock
        self._started_ns = clock()
        self._events: list[Observation] = []

    def record(self, kind: ObservationKind, detail: str) -> None:
        self._events.append(Observation(kind, detail, self._clock() - self._started_ns))

    @property
    def events(self) -> tuple[Observation, ...]:
        return tuple(self._events)


class ObservationPolicy(Protocol):
    """External observer for facts not knowable by the worker runtime."""

    def observe(
        self,
        scenario: SyntheticScenario,
        phase: CampaignPhase,
        receipt: ExecutionReceipt,
        log: ObservationLog,
    ) -> None: ...


@dataclass(frozen=True)
class SyntheticRun:
    scenario: SyntheticScenario
    phase: CampaignPhase
    receipt: ExecutionReceipt
    observations: tuple[Observation, ...]
    started_at: datetime
    finished_at: datetime
    evidence_ref: str

    @property
    def rework_count(self) -> int:
        return sum(event.kind is ObservationKind.REWORK for event in self.observations)

    @property
    def intervention_count(self) -> int:
        return sum(
            event.kind is ObservationKind.ETHERNIAN_INTERVENTION
            for event in self.observations
        )

    @property
    def intent_alignment(self) -> float:
        observed = {
            event.detail
            for event in self.observations
            if event.kind is ObservationKind.INTENT_CHECK
        }
        required = set(self.scenario.required_intent_checks)
        return round(len(required & observed) / len(required), 6)

    def as_evidence(self) -> TrialEvidence:
        return TrialEvidence(
            scenario_id=self.scenario.scenario_id,
            phase=self.phase,
            role=self.scenario.role,
            receipt=self.receipt,
            started_at=self.started_at,
            finished_at=self.finished_at,
            rework_count=self.rework_count,
            ethernian_interventions=self.intervention_count,
            intent_alignment=self.intent_alignment,
            evidence_refs=(self.evidence_ref,),
        )


def default_scenarios() -> tuple[SyntheticScenario, ...]:
    """Public, invented inputs only; no customer or production material."""

    definitions = (
        (
            BenchmarkRole.RESEARCH,
            "Compare documented retry policies for an invented queue",
            ("bounded exponential delay", "idempotent message", "dead-letter route"),
            "research.json",
        ),
        (
            BenchmarkRole.ARCHITECT,
            "Design an acyclic three-stage fruit sorting pipeline",
            ("ingest", "classify", "publish"),
            "architecture.json",
        ),
        (
            BenchmarkRole.BUILD,
            "Normalize invented fruit labels into stable slugs",
            ("Red Apple", "green-pear", "YELLOW BANANA"),
            "implementation.json",
        ),
        (
            BenchmarkRole.TEST,
            "Evaluate boundary cases for a pure integer clamp",
            ("-1", "0", "9", "10"),
            "test-results.json",
        ),
        (
            BenchmarkRole.AUDIT,
            "Audit an invented manifest for unsafe path traversal",
            ("docs/guide.md", "src/example.py", "tests/test_example.py"),
            "audit.json",
        ),
    )
    scenarios = []
    for role, objective, items, artifact in definitions:
        role_name = role.value.lower()
        scenarios.append(
            SyntheticScenario(
                scenario_id=f"safe-{role_name}-v1",
                role=role,
                objective=objective,
                input_items=items,
                expected_artifact=f"synthetic/{role_name}/{artifact}",
                required_intent_checks=("scope", "synthetic-only", "no-promotion"),
            )
        )
    return tuple(scenarios)


_ROLE_TO_KIND = {
    BenchmarkRole.RESEARCH: TaskKind.RESEARCH,
    BenchmarkRole.ARCHITECT: TaskKind.ARCHITECT,
    BenchmarkRole.BUILD: TaskKind.BUILD,
    BenchmarkRole.TEST: TaskKind.TEST,
    BenchmarkRole.AUDIT: TaskKind.AUDIT,
}


class SyntheticExecutor:
    """Executes small deterministic transformations and records observed work."""

    def __init__(
        self,
        scenario: SyntheticScenario,
        observations: ObservationLog,
    ) -> None:
        self.scenario = scenario
        self.observations = observations

    def execute(self, task, *, sandbox_policy, attestation) -> WorkerExecution:
        if task.intent_fingerprint != SYNTHETIC_INTENT:
            raise ValueError("SYNTHETIC_INTENT_MISMATCH")
        result = self._perform_role_work()
        for check in self.scenario.required_intent_checks:
            self.observations.record(ObservationKind.INTENT_CHECK, check)

        checks = (
            "SYNTHETIC_INPUT_ONLY",
            "INTENT_FINGERPRINT_MATCH",
            "NO_INTENT_MUTATION",
            "NO_ASSET_PROMOTION",
            f"RESULT_SHA256:{hashlib.sha256(result.encode()).hexdigest()}",
        )
        return WorkerExecution(
            TaskResult((self.scenario.expected_artifact,), checks, "PASS"),
            (self.scenario.expected_artifact,),
        )

    def _perform_role_work(self) -> str:
        values = self.scenario.input_items
        for value in values:
            self.observations.record(ObservationKind.WORK, hashlib.sha256(value.encode()).hexdigest())
        if self.scenario.role is BenchmarkRole.RESEARCH:
            return json.dumps(sorted(values), separators=(",", ":"))
        if self.scenario.role is BenchmarkRole.ARCHITECT:
            return "->".join(values)
        if self.scenario.role is BenchmarkRole.BUILD:
            return json.dumps([value.casefold().replace(" ", "-") for value in values])
        if self.scenario.role is BenchmarkRole.TEST:
            return json.dumps([max(0, min(9, int(value))) for value in values])
        return json.dumps([str(PurePosixPath(value)) for value in values])


def _task_for(scenario: SyntheticScenario, phase: CampaignPhase) -> TaskContract:
    task_id = uuid5(NAMESPACE_URL, f"apf-027:{phase.value}:{scenario.scenario_id}")
    return TaskContract(
        task_id=task_id,
        kind=_ROLE_TO_KIND[scenario.role],
        intent_fingerprint=SYNTHETIC_INTENT,
        objective=scenario.objective,
        allowed_paths=(f"synthetic/{scenario.role.value.lower()}",),
        expected_artifacts=(scenario.expected_artifact,),
    )


def execute_synthetic_run(
    scenario: SyntheticScenario,
    phase: CampaignPhase,
    *,
    clock: NanoClock = monotonic_ns,
    wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    observer: ObservationPolicy | None = None,
) -> SyntheticRun:
    orchestrator = DevelopmentOrchestrator()
    task = orchestrator.submit(_task_for(scenario, phase))
    observations = ObservationLog(clock)
    receipts = MemoryReceiptSink()
    runtime = ArkaonWorkerRuntime(
        orchestrator,
        Worker(f"arkaon-{scenario.role.value.lower()}", frozenset({task.kind})),
        SyntheticExecutor(scenario, observations),
        receipts,
        worktree_root="/tmp/apf-027-synthetic",
    )
    started_at = wall_clock()
    receipt = runtime.run_once()
    finished_at = wall_clock()
    if receipt is None or receipt.status is not TaskStatus.SUCCEEDED:
        raise RuntimeError("SYNTHETIC_EXECUTION_FAILED")
    if observer is not None:
        observer.observe(scenario, phase, receipt, observations)
    trace = {
        "scenario": scenario.scenario_id,
        "phase": phase.value,
        "intent": receipt.intent_fingerprint,
        "status": receipt.status.value,
        "checks": receipt.checks,
        "events": [(event.kind.value, event.detail) for event in observations.events],
    }
    digest = hashlib.sha256(
        json.dumps(trace, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SyntheticRun(
        scenario=scenario,
        phase=phase,
        receipt=receipt,
        observations=observations.events,
        started_at=started_at,
        finished_at=finished_at,
        evidence_ref=f"evidence://sha256/{digest}",
    )


@dataclass(frozen=True)
class SyntheticCampaignResult:
    runs: tuple[SyntheticRun, ...]
    report: BenchmarkReport

    @property
    def synthetic_pipeline_valid(self) -> bool:
        """Validate plumbing only; this is not real-world efficiency evidence."""

        return all(
            run.receipt.status is TaskStatus.SUCCEEDED
            and run.intent_alignment == 1.0
            and run.as_evidence().safety_violations == 0
            for run in self.runs
        )

    def to_json(self) -> str:
        """Return a canonical, machine-verifiable campaign report."""

        def snapshot(value) -> dict:
            return {
                "total_trials": value.total_trials,
                "success_rate": value.success_rate,
                "average_duration_seconds": value.average_duration_seconds,
                "average_rework": value.average_rework,
                "average_interventions": value.average_interventions,
                "average_intent_alignment": value.average_intent_alignment,
                "safety_violations": value.safety_violations,
                "roles": [
                    {
                        "role": score.role.value,
                        "trials": score.trials,
                        "success_rate": score.success_rate,
                        "average_duration_seconds": score.average_duration_seconds,
                        "average_rework": score.average_rework,
                        "average_interventions": score.average_interventions,
                        "average_intent_alignment": score.average_intent_alignment,
                        "safety_violations": score.safety_violations,
                    }
                    for score in value.scores
                ],
            }

        payload = {
            "campaign": "APF-027",
            "evidence_class": "SYNTHETIC_PIPELINE_ONLY",
            "eligible_for_real_world_efficiency": False,
            "intent_fingerprint": SYNTHETIC_INTENT,
            "synthetic_pipeline_valid": self.synthetic_pipeline_valid,
            "runs": [
                {
                    "scenario_id": run.scenario.scenario_id,
                    "phase": run.phase.value,
                    "role": run.scenario.role.value,
                    "task_id": str(run.receipt.task_id),
                    "status": run.receipt.status.value,
                    "evidence_ref": run.evidence_ref,
                    "rework_count": run.rework_count,
                    "ethernian_interventions": run.intervention_count,
                    "intent_alignment": run.intent_alignment,
                }
                for run in self.runs
            ],
            "report": {
                "baseline": snapshot(self.report.baseline),
                "current": snapshot(self.report.current),
                "intervention_reduction": self.report.intervention_reduction,
                "duration_reduction": self.report.duration_reduction,
                "rework_reduction": self.report.rework_reduction,
                "passed": self.report.passed,
                "blocking_reasons": self.report.blocking_reasons,
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run_synthetic_campaign(
    *,
    scenarios: tuple[SyntheticScenario, ...] | None = None,
    thresholds: BenchmarkThresholds | None = None,
    clock: NanoClock = monotonic_ns,
    wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    observer: ObservationPolicy | None = None,
) -> SyntheticCampaignResult:
    selected = scenarios or default_scenarios()
    if {scenario.role for scenario in selected} != set(BenchmarkRole):
        raise ValueError("SYNTHETIC_ROLE_COVERAGE_REQUIRED")
    campaign = EvidenceBenchmarkCampaign()
    runs = []
    for scenario in selected:
        for phase in CampaignPhase:
            run = execute_synthetic_run(
                scenario,
                phase,
                clock=clock,
                wall_clock=wall_clock,
                observer=observer,
            )
            campaign.record(run.as_evidence())
            runs.append(run)
    return SyntheticCampaignResult(tuple(runs), campaign.evaluate(thresholds=thresholds))
