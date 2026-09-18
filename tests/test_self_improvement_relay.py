import json
import subprocess
from datetime import UTC, datetime

import pytest

from apf.evidence_capability import CollectedEvidence, EvidenceKind
from apf.self_improvement import detect_self_improvement, post_self_improvement
from apf.self_improvement_relay import RelayError, relay_once


class FakePublisher:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, *, request_id, scope_digest, content):
        self.calls.append((request_id, scope_digest, content))
        return f"https://github.test/pull/{len(self.calls)}"


def request(now):
    evidence = CollectedEvidence(
        kind=EvidenceKind.PUBLIC_SNS,
        provenance_complete=True,
        authorization_valid=True,
        license_compatible=True,
        consent_valid=True,
        independently_verified=True,
        fresh=True,
        contains_sensitive_data=False,
        confidence_percent=85,
        independent_source_count=2,
    )
    return detect_self_improvement(
        request_id="relay-001",
        now=now,
        intent_dna="Owner-approved ARKAON improvement only.",
        capability_gap="No real-time review relay.",
        evidence_refs=("sha256:" + "a" * 64, "sha256:" + "b" * 64),
        proposed_change="Relay the request through a durable GitHub PR.",
        expected_benefit="Immediate Eternian review trigger.",
        risks=("Duplicate external delivery.",),
        validation_plan=("Prove idempotent relay receipts.",),
        evidence=evidence,
    )


def test_relay_is_durable_and_idempotent(tmp_path) -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    post_self_improvement(request(now), inbox_root=tmp_path / "inbox", now=now)
    publisher = FakePublisher()

    first = relay_once(foundry_root=tmp_path, publisher=publisher)
    second = relay_once(foundry_root=tmp_path, publisher=publisher)

    assert len(first) == 1
    assert second == ()
    assert len(publisher.calls) == 1
    state = json.loads(
        (tmp_path / "state" / "self-improvement-relay.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["receipts"]["relay-001"]["pull_request_url"].endswith("/1")


def test_relay_rejects_scope_tampering(tmp_path) -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    _, path = post_self_improvement(
        request(now),
        inbox_root=tmp_path / "inbox",
        now=now,
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["proposed_change"] = "Tampered scope"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RelayError, match="SCOPE_DIGEST_MISMATCH"):
        relay_once(foundry_root=tmp_path, publisher=FakePublisher())


def test_relay_rejects_permission_escalation(tmp_path) -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    _, path = post_self_improvement(
        request(now),
        inbox_root=tmp_path / "inbox",
        now=now,
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["deployment_allowed"] = True
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RelayError, match="PROPOSE_ONLY_BOUNDARY_REQUIRED"):
        relay_once(foundry_root=tmp_path, publisher=FakePublisher())


def test_gh_publisher_forces_utf8_and_tolerates_empty_stdout(monkeypatch) -> None:
    from apf.self_improvement_relay import GhPublisher

    observed = {}

    def fake_run(arguments, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(arguments, 0, stdout=None, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = GhPublisher("NurionHoldings/ARKAON-Pattern-Foundry")._run(
        "auth",
        "status",
    )

    assert output == ""
    assert observed["encoding"] == "utf-8"
    assert observed["errors"] == "replace"
