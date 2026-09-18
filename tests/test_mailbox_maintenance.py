import json

from apf.mailbox_maintenance import apply_archive, build_plan


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
