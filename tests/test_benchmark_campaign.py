from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apf.benchmark_campaign import (
    CampaignPhase,
    EvidenceBenchmarkCampaign,
    TrialEvidence,
)
from apf.development_orchestrator import TaskStatus
from apf.role_benchmark import BenchmarkRole
from apf.worker_runtime import ExecutionReceipt

EVIDENCE = "evidence://sha256/" + "a" * 64
NOW = datetime(2026, 9, 15, tzinfo=UTC)


def evidence(
    *,
    scenario: str,
    phase: CampaignPhase,
    role: BenchmarkRole,
    interventions: int,
    duration: int = 10,
    status: TaskStatus = TaskStatus.SUCCEEDED,
    failure_code: str | None = None,
) -> TrialEvidence:
    receipt = ExecutionReceipt(
        task_id=uuid4(),
        worker_id="arkaon",
        intent_fingerprint="intent-v1",
        status=status,
        touched_paths=("src/apf/",),
        checks=("CI_GREEN",),
        failure_code=failure_code,
    )
    return TrialEvidence(
        scenario_id=scenario,
        phase=phase,
        role=role,
        receipt=receipt,
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=duration),
        rework_count=0,
        ethernian_interventions=interventions,
        intent_alignment=0.97,
        evidence_refs=(EVIDENCE,),
    )


def complete_campaign() -> EvidenceBenchmarkCampaign:
    campaign = EvidenceBenchmarkCampaign()
    for role in BenchmarkRole:
        campaign.record(
            evidence(
                scenario=f"scenario-{role.value.lower()}",
                phase=CampaignPhase.BASELINE,
                role=role,
                interventions=4,
                duration=20,
            )
        )
        campaign.record(
            evidence(
                scenario=f"scenario-{role.value.lower()}",
                phase=CampaignPhase.CURRENT,
                role=role,
                interventions=2,
                duration=10,
            )
        )
    return campaign


def test_verified_like_for_like_campaign_passes() -> None:
    campaign = complete_campaign()

    report = campaign.evaluate()

    assert report.passed
    assert report.intervention_reduction == 0.5
    assert report.duration_reduction == 0.5
    assert len(campaign) == 10


def test_unpaired_scenario_fails_closed() -> None:
    campaign = EvidenceBenchmarkCampaign()
    campaign.record(
        evidence(
            scenario="only-baseline",
            phase=CampaignPhase.BASELINE,
            role=BenchmarkRole.RESEARCH,
            interventions=4,
        )
    )

    with pytest.raises(ValueError, match="UNPAIRED"):
        campaign.evaluate()


def test_execution_receipt_cannot_be_reused() -> None:
    campaign = EvidenceBenchmarkCampaign()
    first = evidence(
        scenario="one",
        phase=CampaignPhase.BASELINE,
        role=BenchmarkRole.BUILD,
        interventions=4,
    )
    campaign.record(first)
    reused = TrialEvidence(
        scenario_id="one",
        phase=CampaignPhase.CURRENT,
        role=BenchmarkRole.BUILD,
        receipt=first.receipt,
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=5),
        rework_count=0,
        ethernian_interventions=2,
        intent_alignment=0.97,
        evidence_refs=(EVIDENCE,),
    )

    with pytest.raises(ValueError, match="REUSED_EXECUTION_RECEIPT"):
        campaign.record(reused)


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"verifier": "ARKAON"}, "ETHERNIAN_VERIFIER_REQUIRED"),
        ({"evidence_refs": ("https://example.com/raw",)}, "OPAQUE_EVIDENCE_REQUIRED"),
        ({"started_at": datetime(2026, 9, 15)}, "TIMEZONE_AWARE"),  # noqa: DTZ001
        ({"finished_at": NOW - timedelta(seconds=1)}, "TIME_RANGE"),
    ],
)
def test_untrusted_measurement_is_rejected(changes, error) -> None:
    values = {
        "scenario": "guard",
        "phase": CampaignPhase.BASELINE,
        "role": BenchmarkRole.AUDIT,
        "interventions": 1,
    }
    item = evidence(**values)
    raw = {
        "scenario_id": item.scenario_id,
        "phase": item.phase,
        "role": item.role,
        "receipt": item.receipt,
        "started_at": item.started_at,
        "finished_at": item.finished_at,
        "rework_count": item.rework_count,
        "ethernian_interventions": item.ethernian_interventions,
        "intent_alignment": item.intent_alignment,
        "evidence_refs": item.evidence_refs,
        "verifier": item.verifier,
    }
    raw.update(changes)
    with pytest.raises(ValueError, match=error):
        TrialEvidence(**raw)


def test_scope_violation_is_counted_from_receipt() -> None:
    item = evidence(
        scenario="scope",
        phase=CampaignPhase.CURRENT,
        role=BenchmarkRole.TEST,
        interventions=1,
        status=TaskStatus.FAILED,
        failure_code="SCOPE_VIOLATION",
    )

    assert item.safety_violations == 1
    assert not item.to_trial().passed


def test_campaign_is_immutable_after_evaluation() -> None:
    campaign = complete_campaign()
    campaign.evaluate()

    with pytest.raises(ValueError, match="CAMPAIGN_ALREADY_SEALED"):
        campaign.record(
            evidence(
                scenario="late",
                phase=CampaignPhase.CURRENT,
                role=BenchmarkRole.TEST,
                interventions=0,
            )
        )
    with pytest.raises(ValueError, match="CAMPAIGN_ALREADY_SEALED"):
        campaign.evaluate()
