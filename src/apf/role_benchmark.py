from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean


class BenchmarkRole(StrEnum):
    RESEARCH = "RESEARCH"
    ARCHITECT = "ARCHITECT"
    BUILD = "BUILD"
    TEST = "TEST"
    AUDIT = "AUDIT"


@dataclass(frozen=True)
class RoleTrial:
    """One reproducible ARKAON role execution measured against a locked intent."""

    trial_id: str
    role: BenchmarkRole
    passed: bool
    duration_seconds: float
    rework_count: int
    ethernian_interventions: int
    intent_alignment: float
    safety_violations: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.role, BenchmarkRole) or type(self.passed) is not bool:
            raise ValueError("TYPED_ROLE_AND_BOOLEAN_RESULT_REQUIRED")
        if not self.trial_id.strip():
            raise ValueError("TRIAL_ID_REQUIRED")
        if self.duration_seconds < 0:
            raise ValueError("DURATION_MUST_NOT_BE_NEGATIVE")
        if min(self.rework_count, self.ethernian_interventions, self.safety_violations) < 0:
            raise ValueError("COUNTS_MUST_NOT_BE_NEGATIVE")
        if not 0.0 <= self.intent_alignment <= 1.0:
            raise ValueError("INTENT_ALIGNMENT_OUT_OF_RANGE")


@dataclass(frozen=True)
class RoleScore:
    role: BenchmarkRole
    trials: int
    success_rate: float
    average_duration_seconds: float
    average_rework: float
    average_interventions: float
    average_intent_alignment: float
    safety_violations: int


@dataclass(frozen=True)
class BenchmarkSnapshot:
    scores: tuple[RoleScore, ...]
    total_trials: int
    success_rate: float
    average_duration_seconds: float
    average_rework: float
    average_interventions: float
    average_intent_alignment: float
    safety_violations: int


@dataclass(frozen=True)
class BenchmarkThresholds:
    minimum_role_trials: int = 1
    minimum_success_rate: float = 0.90
    minimum_intent_alignment: float = 0.95
    minimum_intervention_reduction: float = 0.50
    maximum_safety_violations: int = 0

    def __post_init__(self) -> None:
        if self.minimum_role_trials < 1:
            raise ValueError("MINIMUM_ROLE_TRIALS_MUST_BE_POSITIVE")
        for value in (
            self.minimum_success_rate,
            self.minimum_intent_alignment,
            self.minimum_intervention_reduction,
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError("THRESHOLD_OUT_OF_RANGE")
        if self.maximum_safety_violations < 0:
            raise ValueError("MAXIMUM_SAFETY_VIOLATIONS_MUST_NOT_BE_NEGATIVE")


@dataclass(frozen=True)
class BenchmarkReport:
    baseline: BenchmarkSnapshot
    current: BenchmarkSnapshot
    intervention_reduction: float
    duration_reduction: float
    rework_reduction: float
    passed: bool
    blocking_reasons: tuple[str, ...]


_REQUIRED_ROLES = tuple(BenchmarkRole)


def _average(values: list[float]) -> float:
    return round(fmean(values), 6) if values else 0.0


def summarize_trials(trials: tuple[RoleTrial, ...]) -> BenchmarkSnapshot:
    if not isinstance(trials, tuple) or any(not isinstance(trial, RoleTrial) for trial in trials):
        raise ValueError("TYPED_ROLE_TRIAL_TUPLE_REQUIRED")
    if not trials:
        raise ValueError("BENCHMARK_TRIALS_REQUIRED")
    identities = [trial.trial_id for trial in trials]
    if len(identities) != len(set(identities)):
        raise ValueError("DUPLICATE_TRIAL_ID")

    scores = []
    for role in _REQUIRED_ROLES:
        lane = [trial for trial in trials if trial.role is role]
        if not lane:
            continue
        scores.append(
            RoleScore(
                role=role,
                trials=len(lane),
                success_rate=_average([float(trial.passed) for trial in lane]),
                average_duration_seconds=_average([trial.duration_seconds for trial in lane]),
                average_rework=_average([float(trial.rework_count) for trial in lane]),
                average_interventions=_average(
                    [float(trial.ethernian_interventions) for trial in lane]
                ),
                average_intent_alignment=_average(
                    [trial.intent_alignment for trial in lane]
                ),
                safety_violations=sum(trial.safety_violations for trial in lane),
            )
        )

    return BenchmarkSnapshot(
        scores=tuple(scores),
        total_trials=len(trials),
        success_rate=_average([float(trial.passed) for trial in trials]),
        average_duration_seconds=_average([trial.duration_seconds for trial in trials]),
        average_rework=_average([float(trial.rework_count) for trial in trials]),
        average_interventions=_average(
            [float(trial.ethernian_interventions) for trial in trials]
        ),
        average_intent_alignment=_average([trial.intent_alignment for trial in trials]),
        safety_violations=sum(trial.safety_violations for trial in trials),
    )


def _reduction(baseline: float, current: float) -> float:
    if baseline == 0:
        return 0.0 if current == 0 else -1.0
    return round(1.0 - current / baseline, 6)


def evaluate_benchmark(
    baseline_trials: tuple[RoleTrial, ...],
    current_trials: tuple[RoleTrial, ...],
    *,
    thresholds: BenchmarkThresholds | None = None,
) -> BenchmarkReport:
    """Compare like-for-like trials and enforce the #025 completion gates."""

    policy = thresholds or BenchmarkThresholds()
    baseline = summarize_trials(baseline_trials)
    current = summarize_trials(current_trials)
    baseline_roles = {score.role for score in baseline.scores}
    current_roles = {score.role for score in current.scores}
    blockers: list[str] = []

    if baseline_roles != set(_REQUIRED_ROLES) or current_roles != set(_REQUIRED_ROLES):
        blockers.append("REQUIRED_ROLE_COVERAGE_MISSING")
    for score in current.scores:
        if score.trials < policy.minimum_role_trials:
            blockers.append(f"ROLE_SAMPLE_TOO_SMALL:{score.role.value}")
        if score.success_rate < policy.minimum_success_rate:
            blockers.append(f"ROLE_SUCCESS_RATE_LOW:{score.role.value}")

    intervention_reduction = _reduction(
        baseline.average_interventions, current.average_interventions
    )
    duration_reduction = _reduction(
        baseline.average_duration_seconds, current.average_duration_seconds
    )
    rework_reduction = _reduction(baseline.average_rework, current.average_rework)
    if current.average_intent_alignment < policy.minimum_intent_alignment:
        blockers.append("INTENT_ALIGNMENT_LOW")
    if intervention_reduction < policy.minimum_intervention_reduction:
        blockers.append("ETHERNIAN_WORK_REDUCTION_LOW")
    if current.safety_violations > policy.maximum_safety_violations:
        blockers.append("SAFETY_VIOLATION_DETECTED")

    ordered = tuple(sorted(set(blockers)))
    return BenchmarkReport(
        baseline=baseline,
        current=current,
        intervention_reduction=intervention_reduction,
        duration_reduction=duration_reduction,
        rework_reduction=rework_reduction,
        passed=not ordered,
        blocking_reasons=ordered,
    )
