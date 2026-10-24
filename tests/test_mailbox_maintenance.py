import json
from datetime import UTC, datetime
from hashlib import sha256

from apf.mailbox_maintenance import (
    apply_archive,
    build_plan,
    reconcile_mailbox_index,
    run_maintenance,
)

NOW = datetime(2031, 1, 1, tzinfo=UTC)


def write_packet(path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")


def test_prioritizes_improvements_and_limits_delivery_to_batch(tmp_path):
    inbox = tmp_path / "inbox"
    write_packet(inbox / "research" / "ordinary.json", status="PENDING", summary="ordinary")
    write_packet(inbox / "eternian-review" / "fix.json", status="PENDING", summary="수정 요청")
    write_packet(inbox / "self-improvement" / "request.json", state="INBOX_POSTED", request_id="one")

    plan = build_plan(inbox, batch_size=2)

    assert [path.name for path in plan.deliver] == ["request.json", "fix.json"]


def test_archives_terminal_and_semantic_duplicate_packets(tmp_path):
    inbox = tmp_path / "inbox"
    common = {"status": "PENDING", "stage": "research", "platform_id": "DEMO", "summary": "same", "payload_digest": "a" * 64}
    write_packet(inbox / "research" / "first.json", **common)
    write_packet(inbox / "research" / "second.json", **common)
    write_packet(inbox / "research" / "done.json", status="FULFILLED", summary="done")

    plan = build_plan(inbox)

    assert [path.name for path in plan.deliver] == ["first.json"]
    assert {path.name for path in plan.archive} == {"second.json", "done.json"}
    assert [path.name for path in plan.duplicates] == ["second.json"]

    moved = apply_archive(plan, inbox_root=inbox, archive_root=tmp_path / "archive")
    assert len(moved) == 2
    assert all(path.is_file() for path in moved)
    assert (inbox / "research" / "first.json").is_file()


def test_does_not_modify_mailbox_when_only_building_plan(tmp_path):
    packet = tmp_path / "inbox" / "research" / "done.json"
    write_packet(packet, status="FULFILLED")

    plan = build_plan(tmp_path / "inbox")

    assert plan.archive == (packet,)
    assert packet.is_file()


def test_packets_without_strong_identity_are_not_deduplicated(tmp_path):
    inbox = tmp_path / "inbox"
    write_packet(inbox / "research" / "one.json", status="PENDING")
    write_packet(inbox / "research" / "two.json", status="PENDING")

    plan = build_plan(inbox)

    assert {path.name for path in plan.deliver} == {"one.json", "two.json"}
    assert plan.duplicates == ()


def test_invalid_json_is_reported_without_archiving(tmp_path):
    invalid = tmp_path / "inbox" / "research" / "invalid.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("{not-json", encoding="utf-8")

    plan = build_plan(tmp_path / "inbox")

    assert plan.invalid == (invalid,)
    assert plan.archive == ()
    assert invalid.is_file()


def test_relayed_self_improvement_is_archived_not_delivered(tmp_path):
    inbox = tmp_path / "inbox"
    request = inbox / "self-improvement" / "smoke.json"
    document = delivery_packet()
    write_packet(request, **document)

    plan = build_plan(inbox, relay_receipts={"smoke-001": {
        "scope_digest": document["scope_digest"], "pull_request_url": "https://github.test/pull/1",
    }})

    assert plan.deliver == ()
    assert plan.relayed == (request,)
    assert plan.archive == (request,)


def delivery_packet():
    scope = {"request_id": "smoke-001", "intent_dna": "approved scope",
             "capability_gap": "delivery gap", "evidence_refs": [],
             "proposed_change": "repair delivery", "expected_benefit": "no lost request",
             "risks": [], "validation_plan": ["test delivery"], "source_tier": "PUBLIC"}
    digest = sha256(json.dumps(scope, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
    return {**scope, "scope_digest": digest, "state": "INBOX_POSTED",
            "schema_version": "apf.self-improvement-request/1.0",
            "production_change_allowed": False, "automatic_merge_allowed": False,
            "deployment_allowed": False}


def test_non_utf8_packet_cannot_stop_or_be_archived_by_maintenance(tmp_path):
    bad = tmp_path / "inbox/research/000-bad.json"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\xff\xfe")
    good = bad.with_name("001-good.json")
    write_packet(good, status="PENDING")
    report = run_maintenance(foundry_root=tmp_path, apply_archive_changes=True)
    assert report["counts"]["invalid"] == 1
    assert report["counts"]["pending"] == 1
    assert bad.read_bytes() == b"\xff\xfe"
    assert good.exists()


def test_receipt_scope_or_boundary_mismatch_never_archives(tmp_path):
    inbox = tmp_path / "inbox"
    packet = inbox / "self-improvement/request.json"
    original = delivery_packet()
    receipt = {"smoke-001": {"scope_digest": original["scope_digest"],
                              "pull_request_url": "https://github.test/pull/1"}}
    changed = {**original, "proposed_change": "tampered"}
    for document in (changed, {**original, "deployment_allowed": True}):
        write_packet(packet, **document)
        plan = build_plan(inbox, relay_receipts=receipt)
        assert plan.invalid == (packet,)
        assert plan.archive == ()
        assert packet.exists()


def test_wrong_or_incomplete_receipt_is_not_delivery_proof(tmp_path):
    packet = tmp_path / "inbox/self-improvement/request.json"
    document = delivery_packet()
    write_packet(packet, **document)
    for receipt in ({"scope_digest": "wrong", "pull_request_url": "https://github.test/pull/1"},
                    {"scope_digest": document["scope_digest"]}):
        plan = build_plan(tmp_path / "inbox", relay_receipts={"smoke-001": receipt})
        assert plan.invalid == (packet,)
        assert plan.archive == ()


def test_receipt_for_same_id_does_not_archive_research(tmp_path):
    packet = tmp_path / "inbox/research/request.json"
    document = delivery_packet()
    write_packet(packet, **document)
    plan = build_plan(tmp_path / "inbox", relay_receipts={"smoke-001": {
        "scope_digest": document["scope_digest"], "pull_request_url": "https://github.test/pull/1"}})
    assert plan.pending == (packet,)
    assert plan.archive == ()


def test_unknown_receipt_schema_and_non_object_entries_cannot_archive(tmp_path):
    packet = tmp_path / "inbox/self-improvement/request.json"
    document = delivery_packet()
    write_packet(packet, **document)
    state_path = tmp_path / "state/self-improvement-relay.json"
    for state in (
        {"schema_version": "unknown", "receipts": {"smoke-001": {
            "scope_digest": document["scope_digest"], "pull_request_url": "https://github.test/pull/1"}}},
        {"schema_version": "apf.self-improvement-relay-state/1.0",
         "receipts": {"smoke-001": "not-a-receipt"}},
    ):
        write_packet(state_path, **state)
        report = run_maintenance(foundry_root=tmp_path, apply_archive_changes=True)
        assert report["counts"]["pending"] == 1
        assert report["counts"]["archived"] == 0
        assert packet.exists()


def test_reconcile_preserves_pending_when_only_transport_was_archived(tmp_path):
    inbox = tmp_path / "inbox" / "research"
    inbox.mkdir(parents=True)
    archived_name = "done-research.json"
    archive_target = tmp_path / "archive" / "mailbox" / "2026-09-25" / "research" / archived_name
    archive_target.parent.mkdir(parents=True)
    write_packet(archive_target, status="PENDING", summary="archived packet")
    items = tmp_path / "state" / "mailbox" / "items"
    items.mkdir(parents=True)
    (items / "ghost123456789abc.json").write_text(
        json.dumps(
            {
                "item_id": "ghost123456789abc",
                "status": "PENDING",
                "payload_path": f"inbox/research/{archived_name}",
                "platform_id": "DEMO",
                "summary": "ghost",
            }
        ),
        encoding="utf-8",
    )
    write_packet(inbox / "active.json", status="PENDING", summary="still active")

    report = reconcile_mailbox_index(foundry_root=tmp_path, now=NOW)

    ghost = json.loads((items / "ghost123456789abc.json").read_text(encoding="utf-8"))
    assert ghost["status"] == "PENDING"
    assert ghost["reconcile_reason"] == "payload_archived"
    assert report["counts"]["payload_archived"] == 1
    assert report["counts"]["still_pending"] == 0


def test_plan_keeps_all_pending_while_selecting_batch(tmp_path):
    inbox = tmp_path / "inbox"
    for index in range(5):
        write_packet(inbox / "research" / f"{index}.json", status="PENDING")

    plan = build_plan(inbox, batch_size=2)

    assert len(plan.pending) == 5
    assert len(plan.deliver) == 2


def test_missing_payload_is_not_fulfillment(tmp_path):
    item = tmp_path / "state/mailbox/items/missing.json"
    write_packet(item, item_id="missing", status="PENDING",
                 payload_path="inbox/research/lost.json")
    report = reconcile_mailbox_index(foundry_root=tmp_path, now=NOW)
    document = json.loads(item.read_text())
    assert document["status"] == "PENDING"
    assert document["reconcile_reason"] == "payload_missing"
    assert report["counts"]["payload_missing"] == 1
    assert report["counts"]["fulfillment_completed"] == 0


def test_same_named_archive_in_another_stage_is_not_evidence(tmp_path):
    item = tmp_path / "state/mailbox/items/same.json"
    write_packet(item, item_id="same", status="PENDING",
                 payload_path="inbox/research/same.json")
    write_packet(tmp_path / "archive/mailbox/2026-10-24/operator-decision/same.json",
                 status="PENDING")
    report = reconcile_mailbox_index(foundry_root=tmp_path, now=NOW)
    assert report["counts"]["payload_archived"] == 0
    document = json.loads(item.read_text())
    assert document["status"] == "PENDING"
    assert "archived_payload_path" not in document


def test_completed_fulfillment_can_close_pending(tmp_path):
    item = tmp_path / "state/mailbox/items/done.json"
    write_packet(item, item_id="done", status="PENDING",
                 payload_path="inbox/research/done.json")
    write_packet(tmp_path / "state/mailbox/fulfillment-queue/task.json",
                 item_id="done", status="COMPLETED")
    report = reconcile_mailbox_index(foundry_root=tmp_path, now=NOW)
    assert json.loads(item.read_text())["status"] == "FULFILLED"
    assert report["counts"]["fulfillment_completed"] == 1


def test_reconcile_rejects_paths_outside_inbox(tmp_path):
    for index, path in enumerate(("../outside.json", "/tmp/outside.json",
                                 "inbox/research/../../outside.json", "", "C:\\outside.json")):
        write_packet(tmp_path / f"state/mailbox/items/{index}.json",
                     status="PENDING", payload_path=path)
    report = reconcile_mailbox_index(foundry_root=tmp_path, now=NOW)
    assert report["counts"]["invalid_payload_path"] == 5
    assert report["counts"]["fulfillment_completed"] == 0
