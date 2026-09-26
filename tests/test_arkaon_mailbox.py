import json
from datetime import UTC, datetime
from hashlib import sha256

from apf.arkaon_mailbox import (
    ArkaonMailbox,
    FulfillmentAssignee,
    MailboxItemStatus,
    VisitorKind,
)

NOW = datetime(2031, 1, 1, tzinfo=UTC)


def _inbox_packet(tmp_path, stage: str, packet_id: str, summary: str) -> None:
    folder = tmp_path / "inbox" / stage
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{packet_id}.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.test/v1",
                "packet_id": packet_id,
                "stage": stage,
                "platform_id": "NARANG_RIDER",
                "summary": summary,
            }
        ),
        encoding="utf-8",
    )


def test_mailbox_sync_and_visitor_delivery_to_user(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-mailbox-delivery.json").write_text(
        '{"schema_version":"apf.arkaon-mailbox-delivery/v1"}', encoding="utf-8"
    )
    _inbox_packet(tmp_path, "eternian-review", "pkt-1", "waitlist capability gap")
    mailbox = ArkaonMailbox(foundry_root=tmp_path)
    synced = mailbox.sync_from_inbox(now=NOW)
    assert len(synced) == 1
    assert synced[0].status is MailboxItemStatus.PENDING
    message = mailbox.deliver_on_visitor_connect(visitor=VisitorKind.ETERNIAN, now=NOW)
    assert message is not None
    assert "waitlist" in message.body
    assert mailbox.list_items(status=MailboxItemStatus.DELIVERED)


def test_user_approval_queues_fulfillment_for_assignee(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-mailbox-delivery.json").write_text(
        '{"schema_version":"apf.arkaon-mailbox-delivery/v1"}', encoding="utf-8"
    )
    _inbox_packet(tmp_path, "operator-decision", "pkt-op", "operator priority gap")
    mailbox = ArkaonMailbox(foundry_root=tmp_path)
    mailbox.sync_from_inbox(now=NOW)
    message = mailbox.deliver_on_visitor_connect(visitor=VisitorKind.BEOM, now=NOW)
    assert message is not None
    digest = sha256(b"user-approved").hexdigest()
    tasks = mailbox.user_approve_delivery(message_id=message.message_id, approval_digest=digest, now=NOW)
    assert tasks
    assert tasks[0].assignee is FulfillmentAssignee.BEOM
    queued = mailbox.list_fulfillment_queue(assignee=FulfillmentAssignee.BEOM)
    assert len(queued) == 1
    completed = mailbox.complete_fulfillment(
        task_id=queued[0].task_id, now=NOW, completion_note="secured capability draft"
    )
    assert completed.status == "COMPLETED"
    item = mailbox.list_items(status=MailboxItemStatus.FULFILLED)
    assert len(item) == 1


def test_beom_visitor_delivers_only_beom_assignee(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-mailbox-delivery.json").write_text(
        '{"schema_version":"apf.arkaon-mailbox-delivery/v1"}', encoding="utf-8"
    )
    _inbox_packet(tmp_path, "eternian-review", "pkt-et", "eternian review item")
    _inbox_packet(tmp_path, "operator-decision", "pkt-beom", "operator priority gap")
    mailbox = ArkaonMailbox(foundry_root=tmp_path)
    mailbox.sync_from_inbox(now=NOW)
    message = mailbox.deliver_on_visitor_connect(visitor=VisitorKind.BEOM, now=NOW)
    assert message is not None
    assert len(message.item_ids) == 1
    delivered = mailbox.list_items(status=MailboxItemStatus.DELIVERED)
    assert len(delivered) == 1
    assert delivered[0].assignee is FulfillmentAssignee.BEOM
    assert mailbox.list_items(status=MailboxItemStatus.PENDING)


def test_user_reject_marks_items_rejected(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-mailbox-delivery.json").write_text(
        '{"schema_version":"apf.arkaon-mailbox-delivery/v1"}', encoding="utf-8"
    )
    _inbox_packet(tmp_path, "research", "pkt-r", "research item")
    mailbox = ArkaonMailbox(foundry_root=tmp_path)
    mailbox.sync_from_inbox(now=NOW)
    message = mailbox.deliver_on_visitor_connect(visitor=VisitorKind.ETERNIAN, now=NOW)
    assert message is not None
    mailbox.user_reject_delivery(message_id=message.message_id, now=NOW)
    assert mailbox.list_items(status=MailboxItemStatus.REJECTED)
