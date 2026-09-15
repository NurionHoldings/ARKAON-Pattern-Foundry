import json
from datetime import UTC, datetime, timedelta

import pytest

from apf.benchmark_campaign import CampaignPhase
from apf.development_orchestrator import TaskStatus
from apf.role_benchmark import BenchmarkRole
from apf.synthetic_benchmark import (
    ObservationKind,
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


def test_campaign_executes_all_roles_and_derives_report_from_observations() -> None:
    result = run_synthetic_campaign(clock=StepClock(), wall_clock=WallClock())

    assert len(result.runs) == 10
    assert {run.scenario.role for run in result.runs} == set(BenchmarkRole)
    assert all(run.receipt.status is TaskStatus.SUCCEEDED for run in result.runs)
    assert result.report.passed
    assert result.report.intervention_reduction == 1.0
    assert result.report.current.average_intent_alignment == 1.0
    assert result.report.current.safety_violations == 0
    baseline_events = [
        event
        for run in result.runs
        if run.phase is CampaignPhase.BASELINE
        for event in run.observations
        if event.kind is ObservationKind.ETHERNIAN_INTERVENTION
    ]
    assert len(baseline_events) == sum(
        len(scenario.input_items) for scenario in default_scenarios()
    )


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
    assert payload["report"]["passed"] is True
    assert len(payload["runs"]) == 10
    assert all(run["evidence_ref"].startswith("evidence://sha256/") for run in payload["runs"])


def test_metrics_are_computed_from_event_stream() -> None:
    scenario = default_scenarios()[2]
    baseline = execute_synthetic_run(
        scenario, CampaignPhase.BASELINE, clock=StepClock(), wall_clock=WallClock()
    )
    current = execute_synthetic_run(
        scenario, CampaignPhase.CURRENT, clock=StepClock(), wall_clock=WallClock()
    )

    assert baseline.intervention_count == len(scenario.input_items)
    assert current.intervention_count == 0
    assert baseline.rework_count == current.rework_count == 0
    assert baseline.intent_alignment == current.intent_alignment == 1.0


@pytest.mark.parametrize(
    "objective",
    ("inspect customer records", "read password", "perform asset promotion"),
)
def test_sensitive_or_governed_synthetic_content_is_rejected(objective: str) -> None:
    with pytest.raises(ValueError, match="UNSAFE_SYNTHETIC_CONTENT"):
        SyntheticScenario(
            scenario_id="unsafe",
            role=BenchmarkRole.AUDIT,
            objective=objective,
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
