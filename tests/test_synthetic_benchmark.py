import json
from datetime import UTC, datetime, timedelta

import pytest

from apf.benchmark_campaign import CampaignPhase
from apf.development_orchestrator import TaskStatus
from apf.role_benchmark import BenchmarkRole
from apf.synthetic_benchmark import (
    ObservationKind,
    ObservationLog,
    SyntheticScenario,
    default_scenarios,
    execute_synthetic_run,
    run_synthetic_campaign,
)


class StepClock:
    def __init__(self, step: int = 1_000) -> None:
        self.value = 0
        self.step = step

    def __call__(self) -> int:
        self.value += self.step
        return self.value


class WallClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 15, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(milliseconds=1)
        return current


class RecordedReviewPolicy:
    """Test observer standing in for an external measurement source."""

    def observe(self, scenario, phase, receipt, log: ObservationLog) -> None:
        count = 3 if phase is CampaignPhase.BASELINE else 1
        for index in range(count):
            log.record(ObservationKind.ETHERNIAN_INTERVENTION, f"observed-review-{index}")


def test_campaign_executes_all_roles_and_derives_report_from_observations() -> None:
    result = run_synthetic_campaign(
        clock=StepClock(), wall_clock=WallClock(), observer=RecordedReviewPolicy()
    )

    assert len(result.runs) == 10
    assert {run.scenario.role for run in result.runs} == set(BenchmarkRole)
    assert all(run.receipt.status is TaskStatus.SUCCEEDED for run in result.runs)
    assert result.report.passed
    assert result.report.intervention_reduction == 0.666667
    assert result.report.current.average_intent_alignment == 1.0
    assert result.report.current.safety_violations == 0
    baseline_events = [
        event
        for run in result.runs
        if run.phase is CampaignPhase.BASELINE
        for event in run.observations
        if event.kind is ObservationKind.ETHERNIAN_INTERVENTION
    ]
    assert len(baseline_events) == len(default_scenarios()) * 3


def test_default_campaign_validates_plumbing_without_claiming_efficiency() -> None:
    result = run_synthetic_campaign(clock=StepClock(), wall_clock=WallClock())

    assert result.synthetic_pipeline_valid
    assert not result.report.passed
    assert result.report.intervention_reduction == 0.0
    assert "ETHERNIAN_WORK_REDUCTION_LOW" in result.report.blocking_reasons
    assert all(run.intervention_count == 0 for run in result.runs)


def test_evidence_digest_is_reproducible_and_receipts_are_distinct() -> None:
    scenario = default_scenarios()[0]
    first = execute_synthetic_run(
        scenario, CampaignPhase.CURRENT, clock=StepClock(), wall_clock=WallClock()
    )
    second = execute_synthetic_run(
        scenario, CampaignPhase.CURRENT, clock=StepClock(), wall_clock=WallClock()
    )
    baseline = execute_synthetic_run(
        scenario, CampaignPhase.BASELINE, clock=StepClock(), wall_clock=WallClock()
    )

    assert first.evidence_ref == second.evidence_ref
    assert first.receipt.task_id == second.receipt.task_id
    assert first.receipt.task_id != baseline.receipt.task_id
    assert first.evidence_ref != baseline.evidence_ref


def test_campaign_report_is_canonical_and_contains_observed_evidence() -> None:
    first = run_synthetic_campaign(clock=StepClock(), wall_clock=WallClock())
    second = run_synthetic_campaign(clock=StepClock(), wall_clock=WallClock())

    assert first.to_json() == second.to_json()
    payload = json.loads(first.to_json())
    assert payload["campaign"] == "APF-027"
    assert payload["synthetic_pipeline_valid"] is True
    assert payload["eligible_for_real_world_efficiency"] is False
    assert payload["report"]["passed"] is False
    assert len(payload["runs"]) == 10
    assert all(run["evidence_ref"].startswith("evidence://sha256/") for run in payload["runs"])


def test_metrics_are_computed_from_event_stream() -> None:
    scenario = default_scenarios()[2]
    baseline = execute_synthetic_run(
        scenario,
        CampaignPhase.BASELINE,
        clock=StepClock(),
        wall_clock=WallClock(),
        observer=RecordedReviewPolicy(),
    )
    current = execute_synthetic_run(
        scenario,
        CampaignPhase.CURRENT,
        clock=StepClock(),
        wall_clock=WallClock(),
        observer=RecordedReviewPolicy(),
    )

    assert baseline.intervention_count == 3
    assert current.intervention_count == 1
    assert baseline.rework_count == current.rework_count == 0
    assert baseline.intent_alignment == current.intent_alignment == 1.0


@pytest.mark.parametrize(
    "objective",
    (
        "contact learner@example.com",
        "use api_key=dummyValue123456789",
        "call 010-1234-5678",
    ),
)
def test_learning_safety_scanner_rejects_pii_and_secrets(objective: str) -> None:
    with pytest.raises(ValueError, match="LEARNING_SAFETY_BLOCKED"):
        SyntheticScenario(
            scenario_id="unsafe",
            role=BenchmarkRole.AUDIT,
            objective=objective,
            input_items=("invented",),
            expected_artifact="synthetic/audit/result.json",
            required_intent_checks=("scope",),
        )


def test_learning_safety_scanner_covers_every_input_item() -> None:
    with pytest.raises(ValueError, match="PII_EMAIL"):
        SyntheticScenario(
            scenario_id="unsafe-input",
            role=BenchmarkRole.RESEARCH,
            objective="Compare invented records",
            input_items=("safe", "learner@example.com"),
            expected_artifact="synthetic/research/result.json",
            required_intent_checks=("scope",),
        )


def test_governed_operations_are_rejected_separately() -> None:
    with pytest.raises(ValueError, match="GOVERNED_SYNTHETIC_OPERATION"):
        SyntheticScenario(
            scenario_id="governed",
            role=BenchmarkRole.AUDIT,
            objective="perform asset promotion",
            input_items=("invented",),
            expected_artifact="synthetic/audit/result.json",
            required_intent_checks=("scope",),
        )


def test_role_coverage_fails_closed() -> None:
    with pytest.raises(ValueError, match="SYNTHETIC_ROLE_COVERAGE_REQUIRED"):
        run_synthetic_campaign(
            scenarios=default_scenarios()[:-1],
            clock=StepClock(),
            wall_clock=WallClock(),
        )
