"""Safely register exactly one self-heal review packet in the local ARKAON mailbox.

Run from the repository root:
    python scripts/register_self_heal_review.py

Does not call sync_from_inbox, approve, fulfill, or deploy.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from apf.arkaon_mailbox import ArkaonMailbox, MailboxItem, MailboxItemStatus, FulfillmentAssignee

    relative = Path("inbox/eternian-review/self-heal-api-connectivity-review.json")
    path = root / relative
    if not path.is_file():
        print("ERROR: review packet missing")
        return 2
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        print(f"ERROR: unreadable review packet: {exc}")
        return 2
    required = {
        "schema_version": "arkaon.self-heal.review-request/v1",
        "platform_id": "ARKAON_FOUNDRY",
    }
    if any(document.get(k) != v for k, v in required.items()):
        print("ERROR: unexpected review schema or platform")
        return 2
    packet_id = document.get("packet_id")
    summary = document.get("summary")
    if not isinstance(packet_id, str) or not packet_id.strip() or not isinstance(summary, str) or not summary.strip():
        print("ERROR: packet_id and summary must be nonempty strings")
        return 2
    item_id = sha256(packet_id.encode("utf-8")).hexdigest()[:16]
    mailbox = ArkaonMailbox(foundry_root=root)
    target = mailbox.items_root / f"{item_id}.json"
    if target.exists():
        existing = mailbox._load_item(item_id)
        if existing and existing.source_packet_id == packet_id and existing.payload_path == relative.as_posix():
            print(f"ALREADY_REGISTERED: {item_id} status={existing.status.value}")
            return 0
        print(f"ERROR: item ID collision or conflicting record: {item_id}")
        return 3
    for existing in mailbox.list_items():
        if existing.payload_path == relative.as_posix():
            print(f"ERROR: review path already registered with different packet ID: {existing.item_id}")
            return 3
    item = MailboxItem(
        item_id=item_id,
        source_packet_id=packet_id,
        inbox_stage="eternian-review",
        platform_id="ARKAON_FOUNDRY",
        summary=summary[:2000],
        schema_version=required["schema_version"],
        status=MailboxItemStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        payload_path=relative.as_posix(),
        assignee=FulfillmentAssignee.ETERNIAN,
    )
    try:
        with target.open("x", encoding="utf-8") as stream:
            json.dump(item.to_document(), stream, ensure_ascii=False, indent=2, sort_keys=True)
    except FileExistsError:
        print("ERROR: concurrent registration detected; existing file preserved")
        return 3
    print(f"REGISTERED: {item_id} status=PENDING assignee=eternian")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
