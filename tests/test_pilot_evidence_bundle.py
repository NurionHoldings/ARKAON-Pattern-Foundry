import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apf.benchmark_campaign import CampaignPhase
from apf.development_orchestrator import TaskStatus
from apf.pilot_observation import (
    EthernianObserver,
    EvidenceClass,
    PilotBundleVerificationResult,
    PilotEventKind,
    PilotObservationDraft,
    PilotObservationLedger,
    verify_pilot_observation_bundle,
)
from apf.role_benchmark import BenchmarkRole
from apf.worker_runtime import ExecutionReceipt

NOW = datetime(2026, 9, 16, tzinfo=UTC)
EVIDENCE = "evidence://sha256/" + "c" * 64


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def fixture_bundle() -> tuple[bytes, EthernianObserver, PilotObservationLedger]:
    signer = EthernianObserver(key_id="ethernian-pilot-v1", signing_key=b"k" * 32)
    ledger = PilotObservationLedger(trusted_observer_keys={signer.key_id: signer.public_key})
    for offset, kind in enumerate((PilotEventKind.START, PilotEventKind.FINISH)):
        receipt = None
        if kind is PilotEventKind.FINISH:
            receipt = ExecutionReceipt(
                task_id=uuid4(),
                worker_id="arkaon-build",
                intent_fingerprint="intent-v1",
                status=TaskStatus.SUCCEEDED,
                touched_paths=("src/apf/",),
                checks=("CI_GREEN",),
            )
        draft = PilotObservationDraft(
            event_id=uuid4(),
            trial_id="trial-export",
            scenario_id="scenario-export",
            phase=CampaignPhase.CURRENT,
            role=BenchmarkRole.AUDIT,
            kind=kind,
            observed_at=NOW + timedelta(seconds=offset),
            receipt=receipt,
            intent_alignment=0.99 if receipt else None,
            evidence_refs=(EVIDENCE,) if receipt else (),
        )
        ledger.append(signer.attest(ledger.challenge(draft)))
    return ledger.export_bundle(signer), signer, ledger


def resign(document: dict, signer: EthernianObserver) -> bytes:
    manifest = {
        key: value
        for key, value in document.items()
        if key not in {"bundle_hash", "bundle_signature"}
    }
    manifest_bytes = canonical(manifest)
    document["bundle_hash"] = hashlib.sha256(manifest_bytes).hexdigest()
    document["bundle_signature"] = signer.sign_bundle_manifest(manifest_bytes)
    return canonical(document)


def test_canonical_bundle_is_verified_with_public_key_only() -> None:
    bundle, signer, ledger = fixture_bundle()
    before = ledger.entries

    result = verify_pilot_observation_bundle(
        bundle, trusted_observer_keys={signer.key_id: signer.public_key}
    )

    assert isinstance(result, PilotBundleVerificationResult)
    assert result.evidence_class is EvidenceClass.PILOT_OBSERVATION
    assert result.entry_count == 2
    assert ledger.entries == before
    assert b"signing_key" not in bundle and b"private" not in bundle
    assert canonical(json.loads(bundle)) == bundle


@pytest.mark.parametrize("mutation", ["payload", "truncate", "reorder"])
def test_tamper_truncation_and_reorder_fail_closed(mutation: str) -> None:
    bundle, signer, _ = fixture_bundle()
    document = json.loads(bundle)
    if mutation == "payload":
        document["entries"][0]["scenario_id"] = "scenario-tampered"
        candidate = resign(document, signer)
    elif mutation == "truncate":
        document["entries"].pop()
        candidate = canonical(document)
    else:
        document["entries"].reverse()
        candidate = resign(document, signer)

    with pytest.raises(ValueError):
        verify_pilot_observation_bundle(
            candidate, trusted_observer_keys={signer.key_id: signer.public_key}
        )


def test_wrong_key_and_duplicate_entry_are_rejected() -> None:
    bundle, signer, _ = fixture_bundle()
    wrong = EthernianObserver(key_id=signer.key_id, signing_key=b"x" * 32)
    with pytest.raises(ValueError, match="SIGNATURE"):
        verify_pilot_observation_bundle(
            bundle, trusted_observer_keys={wrong.key_id: wrong.public_key}
        )

    document = json.loads(bundle)
    document["entries"].append(document["entries"][0])
    document["entry_count"] += 1
    candidate = resign(document, signer)
    with pytest.raises(ValueError, match="SCHEMA|CHAIN|DUPLICATE"):
        verify_pilot_observation_bundle(
            candidate, trusted_observer_keys={signer.key_id: signer.public_key}
        )


def test_unknown_unsafe_metadata_and_wrong_evidence_class_are_rejected() -> None:
    bundle, signer, _ = fixture_bundle()
    for mutate in (
        lambda value: value.update({"metadata": "token: abcdefghijklmnop"}),
        lambda value: value.update({"evidence_class": "SYNTHETIC_PIPELINE_ONLY"}),
        lambda value: value["entries"][0].update({"raw_source": "person@example.com"}),
    ):
        document = json.loads(bundle)
        mutate(document)
        candidate = resign(document, signer)
        with pytest.raises(ValueError, match="SCHEMA"):
            verify_pilot_observation_bundle(
                candidate, trusted_observer_keys={signer.key_id: signer.public_key}
            )


def test_noncanonical_and_duplicate_json_fields_are_rejected() -> None:
    bundle, signer, _ = fixture_bundle()
    pretty = json.dumps(json.loads(bundle), indent=2).encode()
    with pytest.raises(ValueError, match="CANONICAL"):
        verify_pilot_observation_bundle(
            pretty, trusted_observer_keys={signer.key_id: signer.public_key}
        )

    duplicated = bundle[:-1] + b',"schema_version":"apf.pilot-observation-bundle/v1"}'
    with pytest.raises(ValueError, match="DUPLICATE"):
        verify_pilot_observation_bundle(
            duplicated, trusted_observer_keys={signer.key_id: signer.public_key}
        )
