from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .development_orchestrator import TaskStatus
from .role_benchmark import (
    BenchmarkReport,
    BenchmarkRole,
    BenchmarkThresholds,
    RoleTrial,
    evaluate_benchmark,
)
from .worker_runtime import ExecutionReceipt

_OPAQUE_EVIDENCE = re.compile(r"\Aevidence://sha256/[0-9a-f]{64}\Z")


class CampaignPhase(StrEnum):
    BASELINE = "BASELINE"
    CURRENT = "CURRENT"


@dataclass(frozen=True)
class TrialEvidence:
    """Verifier-observed inputs for one like-for-like benchmark execution."""

    scenario_id: str
    phase: CampaignPhase
    role: BenchmarkRole
    receipt: ExecutionReceipt
    started_at: datetime
    finished_at: datetime
    rework_count: int
    ethernian_interventions: int
    intent_alignment: float
    evidence_refs: tuple[str, ...]
    verifier: str = "ETHERNIAN"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("SCENARIO_ID_REQUIRED")
        if self.verifier != "ETHERNIAN":
            raise ValueError("ETHERNIAN_VERIFIER_REQUIRED")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("TIMEZONE_AWARE_TIMESTAMPS_REQUIRED")
        if self.finished_at.tzinfo is None or self.finished_at.utcoffset() is None:
            raise ValueError("TIMEZONE_AWARE_TIMESTAMPS_REQUIRED")
        if self.finished_at < self.started_at:
            raise ValueError("INVALID_TRIAL_TIME_RANGE")
        if min(self.rework_count, self.ethernian_interventions) < 0:
            raise ValueError("COUNTS_MUST_NOT_BE_NEGATIVE")
        if not 0.0 <= self.intent_alignment <= 1.0:
            raise ValueError("INTENT_ALIGNMENT_OUT_OF_RANGE")
        if not self.receipt.intent_fingerprint.strip() or not self.receipt.checks:
            raise ValueError("VERIFIABLE_RECEIPT_REQUIRED")
        if not self.evidence_refs or any(
            _OPAQUE_EVIDENCE.fullmatch(reference) is None for reference in self.evidence_refs
        ):
            raise ValueError("OPAQUE_EVIDENCE_REQUIRED")

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def safety_violations(self) -> int:
        return int(
            self.receipt.failure_code == "SCOPE_VIOLATION"
            or "SCOPE_CHECK_FAILED" in self.receipt.checks
        )

    def to_trial(self) -> RoleTrial:
        return RoleTrial(
            trial_id=f"{self.phase.value}:{self.scenario_id}:{self.role.value}",
            role=self.role,
            passed=self.receipt.status is TaskStatus.SUCCEEDED,
            duration_seconds=self.duration_seconds,
            rework_count=self.rework_count,
            ethernian_interventions=self.ethernian_interventions,
            intent_alignment=self.intent_alignment,
            safety_violations=self.safety_violations,
        )


class EvidenceBenchmarkCampaign:
    """Pairs baseline/current executions without trusting worker self-reported metrics."""

    def __init__(self) -> None:
        self._evidence: dict[tuple[CampaignPhase, str, BenchmarkRole], TrialEvidence] = {}
        self._receipt_ids: set[UUID] = set()
        self._sealed = False

    def record(self, evidence: TrialEvidence) -> None:
        if self._sealed:
            raise ValueError("CAMPAIGN_ALREADY_SEALED")
        key = (evidence.phase, evidence.scenario_id, evidence.role)
        if key in self._evidence:
            raise ValueError("DUPLICATE_SCENARIO_ROLE_PHASE")
        if evidence.receipt.task_id in self._receipt_ids:
            raise ValueError("REUSED_EXECUTION_RECEIPT")
        self._evidence[key] = evidence
        self._receipt_ids.add(evidence.receipt.task_id)

    def evaluate(
        self, *, thresholds: BenchmarkThresholds | None = None
    ) -> BenchmarkReport:
        if self._sealed:
            raise ValueError("CAMPAIGN_ALREADY_SEALED")
        baseline_keys = {
            (scenario, role)
            for phase, scenario, role in self._evidence
            if phase is CampaignPhase.BASELINE
        }
        current_keys = {
            (scenario, role)
            for phase, scenario, role in self._evidence
            if phase is CampaignPhase.CURRENT
        }
        if baseline_keys != current_keys:
            raise ValueError("UNPAIRED_BENCHMARK_SCENARIOS")
        if not baseline_keys:
            raise ValueError("BENCHMARK_EVIDENCE_REQUIRED")

        baseline = tuple(
            evidence.to_trial()
            for key, evidence in sorted(
                self._evidence.items(),
                key=lambda item: (
                    item[0][0].value,
                    item[0][1],
                    item[0][2].value,
                ),
            )
            if key[0] is CampaignPhase.BASELINE
        )
        current = tuple(
            evidence.to_trial()
            for key, evidence in sorted(
                self._evidence.items(),
                key=lambda item: (
                    item[0][0].value,
                    item[0][1],
                    item[0][2].value,
                ),
            )
            if key[0] is CampaignPhase.CURRENT
        )
        report = evaluate_benchmark(baseline, current, thresholds=thresholds)
        self._sealed = True
        return report

    def __len__(self) -> int:
        return len(self._evidence)
