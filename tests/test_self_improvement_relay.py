import json
import subprocess
from datetime import UTC, datetime

from apf.evidence_capability import CollectedEvidence, EvidenceKind
from apf.self_improvement import detect_self_improvement, post_self_improvement
from apf.self_improvement_relay import relay_cycle, relay_once


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

    first, first_blocked = relay_once(foundry_root=tmp_path, publisher=publisher)
    second, second_blocked = relay_once(foundry_root=tmp_path, publisher=publisher)

    assert len(first) == 1
    assert second == ()
    assert first_blocked == second_blocked == ()
    assert len(publisher.calls) == 1
    state = json.loads(
        (tmp_path / "state" / "self-improvement-relay.json").read_text(encoding="utf-8")
    )
    assert state["receipts"]["relay-001"]["pull_request_url"].endswith("/1")


def test_relay_quarantines_scope_tampering(tmp_path) -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    _, path = post_self_improvement(
        request(now),
        inbox_root=tmp_path / "inbox",
        now=now,
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["proposed_change"] = "Tampered scope"
    path.write_text(json.dumps(document), encoding="utf-8")

    delivered, blocked = relay_once(foundry_root=tmp_path, publisher=FakePublisher())
    assert delivered == ()
    assert blocked[0].reason == "SCOPE_DIGEST_MISMATCH"
    assert not path.exists()


def test_relay_quarantines_permission_escalation(tmp_path) -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    _, path = post_self_improvement(
        request(now),
        inbox_root=tmp_path / "inbox",
        now=now,
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["deployment_allowed"] = True
    path.write_text(json.dumps(document), encoding="utf-8")

    delivered, blocked = relay_once(foundry_root=tmp_path, publisher=FakePublisher())
    assert delivered == ()
    assert blocked[0].reason == "PROPOSE_ONLY_BOUNDARY_REQUIRED"


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


def test_relay_cycle_delivers_then_archives_transport_packet(tmp_path) -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    _, path = post_self_improvement(
        request(now),
        inbox_root=tmp_path / "inbox",
        now=now,
    )

    cycle = relay_cycle(foundry_root=tmp_path, publisher=FakePublisher())

    assert len(cycle.delivered) == 1
    assert cycle.blocked == ()
    assert cycle.approvals is None
    assert cycle.mailbox["counts"]["relayed"] == 1
    assert cycle.mailbox["counts"]["archived"] == 1
    assert not path.exists()
    archived = list((tmp_path / "archive" / "mailbox").rglob(path.name))
    assert len(archived) == 1
    report = json.loads(
        (tmp_path / "state" / "mailbox-maintenance-latest.json").read_text(encoding="utf-8")
    )
    assert report["counts"]["pending"] == 0


def test_corrupt_packet_does_not_block_later_valid_request(tmp_path) -> None:
    inbox = tmp_path / "inbox" / "self-improvement"
    inbox.mkdir(parents=True)
    corrupt = inbox / "000-corrupt.json"
    corrupt.write_text('{"broken":', encoding="utf-8")
    now = datetime(2026, 9, 18, tzinfo=UTC)
    post_self_improvement(request(now), inbox_root=tmp_path / "inbox", now=now)
    publisher = FakePublisher()

    delivered, blocked = relay_once(foundry_root=tmp_path, publisher=publisher)

    assert [item.request_id for item in delivered] == ["relay-001"]
    assert len(blocked) == 1
    assert blocked[0].source_name == corrupt.name
    assert blocked[0].reason == "JSONDECODEERROR"
    quarantine = tmp_path / "quarantine" / "self-improvement"
    assert (quarantine / blocked[0].quarantine_name).is_file()
    evidence = json.loads(
        (quarantine / blocked[0].quarantine_name).with_suffix(".blocked.json").read_text()
    )
    assert evidence["state"] == "BLOCKED"
    assert evidence["evidence_digest"] == blocked[0].evidence_digest
