from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apf.benchmark_campaign import CampaignPhase
from apf.development_orchestrator import TaskStatus
from apf.learning_safety import LearningSafetyViolation
from apf.pilot_observation import (
    EthernianObserver,
    EvidenceClass,
    PilotEventKind,
    PilotObservationDraft,
    PilotObservationLedger,
)
from apf.role_benchmark import BenchmarkRole, BenchmarkThresholds
from apf.worker_runtime import ExecutionReceipt

NOW = datetime(2026, 9, 16, tzinfo=UTC)
EVIDENCE = "evidence://sha256/" + "b" * 64


def observer() -> EthernianObserver:
    return EthernianObserver(key_id="ethernian-pilot-v1", signing_key=b"k" * 32)


def receipt() -> ExecutionReceipt:
    return ExecutionReceipt(
        task_id=uuid4(),
        worker_id="arkaon-build",
        intent_fingerprint="intent-v1",
        status=TaskStatus.SUCCEEDED,
        touched_paths=("src/apf/",),
        checks=("CI_GREEN",),
        failure_code=None,
    )


def draft(
    kind: PilotEventKind,
    at: datetime,
    *,
    scenario: str = "scenario-build",
    phase: CampaignPhase = CampaignPhase.BASELINE,
    role: BenchmarkRole = BenchmarkRole.BUILD,
    trial: str = "trial-build-baseline",
    execution: ExecutionReceipt | None = None,
) -> PilotObservationDraft:
    return PilotObservationDraft(
        event_id=uuid4(),
        trial_id=trial,
        scenario_id=scenario,
        phase=phase,
        role=role,
        kind=kind,
        observed_at=at,
        receipt=execution,
        intent_alignment=0.98 if kind is PilotEventKind.FINISH else None,
        evidence_refs=(EVIDENCE,) if kind is PilotEventKind.FINISH else (),
    )


def test_signed_ledger_derives_observer_metrics() -> None:
    ledger = PilotObservationLedger(observer())
    ledger.append(draft(PilotEventKind.START, NOW))
    ledger.append(draft(PilotEventKind.INTERVENTION, NOW + timedelta(seconds=1)))
    ledger.append(draft(PilotEventKind.REWORK, NOW + timedelta(seconds=2)))
    ledger.append(
        draft(PilotEventKind.FINISH, NOW + timedelta(seconds=8), execution=receipt())
    )

    campaign = ledger.to_campaign()
    evidence = next(iter(campaign._evidence.values()))

    assert evidence.duration_seconds == 8
    assert evidence.ethernian_interventions == 1
    assert evidence.rework_count == 1
    assert all(entry.observer_id == "ETHERNIAN" for entry in ledger.entries)
    assert all(
        entry.evidence_class is EvidenceClass.PILOT_OBSERVATION
        for entry in ledger.entries
    )


def test_hash_chain_detects_post_append_mutation() -> None:
    ledger = PilotObservationLedger(observer())
    ledger.append(draft(PilotEventKind.START, NOW))
    finish = ledger.append(
        draft(PilotEventKind.FINISH, NOW + timedelta(seconds=2), execution=receipt())
    )
    ledger._entries[-1] = replace(finish, entry_hash="f" * 64)

    with pytest.raises(ValueError, match="TAMPERING|CHAIN"):
        ledger.verify_integrity()


def test_signature_detects_forged_observer_event() -> None:
    ledger = PilotObservationLedger(observer())
    entry = ledger.append(draft(PilotEventKind.START, NOW))
    ledger._entries[0] = replace(entry, observer_signature="0" * 64)

    with pytest.raises(ValueError, match="TAMPERING"):
        ledger.verify_integrity()


def test_duplicate_time_regression_and_receipt_reuse_fail_closed() -> None:
    ledger = PilotObservationLedger(observer())
    first = draft(PilotEventKind.START, NOW)
    ledger.append(first)
    with pytest.raises(ValueError, match="DUPLICATE_EVENT"):
        ledger.append(first)
    with pytest.raises(ValueError, match="TIME_REGRESSION"):
        ledger.append(draft(PilotEventKind.REWORK, NOW - timedelta(seconds=1)))

    execution = receipt()
    ledger.append(
        draft(PilotEventKind.FINISH, NOW + timedelta(seconds=2), execution=execution)
    )
    with pytest.raises(ValueError, match="REUSED_EXECUTION_RECEIPT"):
        ledger.append(
            draft(
                PilotEventKind.FINISH,
                NOW + timedelta(seconds=3),
                scenario="another",
                trial="another-trial",
                execution=execution,
            )
        )


@pytest.mark.parametrize(
    "value",
    ["person@example.com", "token: abcdefghijklmnop", "https://raw.example/path"],
)
def test_raw_pii_secret_and_nonopaque_evidence_are_rejected(value: str) -> None:
    values = {
        "event_id": uuid4(),
        "trial_id": "trial-safe",
        "scenario_id": value,
        "phase": CampaignPhase.BASELINE,
        "role": BenchmarkRole.AUDIT,
        "kind": PilotEventKind.START,
        "observed_at": NOW,
    }
    if value.startswith("https"):
        values["scenario_id"] = "scenario-safe"
        values["kind"] = PilotEventKind.FINISH
        values["receipt"] = receipt()
        values["intent_alignment"] = 1.0
        values["evidence_refs"] = (value,)
    with pytest.raises((ValueError, LearningSafetyViolation)):
        PilotObservationDraft(**values)


def test_secret_in_worker_receipt_is_rejected_before_storage() -> None:
    unsafe_receipt = replace(receipt(), checks=("token: abcdefghijklmnop",))

    with pytest.raises(LearningSafetyViolation, match="SECRET_TOKEN"):
        draft(PilotEventKind.FINISH, NOW, execution=unsafe_receipt)


def test_incomplete_or_wrongly_ordered_trial_is_rejected() -> None:
    ledger = PilotObservationLedger(observer())
    ledger.append(
        draft(PilotEventKind.FINISH, NOW, execution=receipt())
    )

    with pytest.raises(ValueError, match="BOUNDARY|ORDER"):
        ledger.to_campaign()


def test_insufficient_paired_role_evidence_cannot_pass() -> None:
    ledger = PilotObservationLedger(observer())
    for index, phase in enumerate(CampaignPhase):
        trial = f"trial-build-{phase.value.lower()}"
        ledger.append(
            draft(
                PilotEventKind.START,
                NOW + timedelta(seconds=index * 10),
                phase=phase,
                trial=trial,
            )
        )
        ledger.append(
            draft(
                PilotEventKind.FINISH,
                NOW + timedelta(seconds=index * 10 + 5),
                phase=phase,
                trial=trial,
                execution=receipt(),
            )
        )

    report = ledger.evaluate(
        thresholds=BenchmarkThresholds(minimum_intervention_reduction=0)
    )

    assert not report.passed
    assert "REQUIRED_ROLE_COVERAGE_MISSING" in report.blocking_reasons


def test_ledger_is_sealed_after_evaluation_attempt() -> None:
    ledger = PilotObservationLedger(observer())
    # A structurally complete but role-incomplete campaign evaluates to a failed report.
    for index, phase in enumerate(CampaignPhase):
        trial = f"trial-{phase.value.lower()}"
        ledger.append(draft(PilotEventKind.START, NOW + timedelta(seconds=index * 4), phase=phase, trial=trial))
        ledger.append(
            draft(
                PilotEventKind.FINISH,
                NOW + timedelta(seconds=index * 4 + 2),
                phase=phase,
                trial=trial,
                execution=receipt(),
            )
        )
    ledger.evaluate(thresholds=BenchmarkThresholds(minimum_intervention_reduction=0))

    with pytest.raises(ValueError, match="SEALED"):
        ledger.append(draft(PilotEventKind.START, NOW + timedelta(seconds=20)))
