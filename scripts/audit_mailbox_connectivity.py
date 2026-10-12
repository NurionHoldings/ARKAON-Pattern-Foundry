"""Read-only audit of the ARKAON mailbox and self-heal connectivity review.

Usage: python scripts/audit_mailbox_connectivity.py
No approvals, synchronization, or deployment are performed.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def audit(root: Path) -> dict[str, object]:
    root = root.resolve()
    items_dir = root / "state" / "mailbox" / "items"
    review = root / "inbox" / "eternian-review" / "self-heal-api-connectivity-review.json"
    statuses: Counter[str] = Counter()
    stages: Counter[str] = Counter()
    assignees: Counter[str] = Counter()
    invalid: list[str] = []
    matching: list[str] = []
    count = 0
    for path in sorted(items_dir.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8-sig"))
            if item.get("schema_version") != "apf.mailbox-item/v1":
                invalid.append(path.name)
                continue
            count += 1
            statuses[str(item.get("status", "UNKNOWN"))] += 1
            stages[str(item.get("inbox_stage", "UNKNOWN"))] += 1
            assignees[str(item.get("assignee", "UNKNOWN"))] += 1
            if "self-heal-api-connectivity-review" in str(item.get("payload_path", "")):
                matching.append(str(item.get("item_id", "")))
        except (OSError, ValueError, TypeError):
            invalid.append(path.name)
    review_details: dict[str, object] = {"exists": review.is_file()}
    if review.is_file():
        try:
            packet = json.loads(review.read_text(encoding="utf-8-sig"))
            review_details.update({
                "schema_version": packet.get("schema_version"),
                "has_packet_id": bool(packet.get("packet_id")),
                "has_platform_id": bool(packet.get("platform_id")),
                "has_summary": bool(packet.get("summary")),
                "compatible_stage": "eternian-review",
            })
        except (OSError, ValueError, TypeError):
            review_details["parse_error"] = True
    return {
        "read_only": True,
        "mailbox_item_count": count,
        "statuses": dict(statuses),
        "stages": dict(stages),
        "assignees": dict(assignees),
        "invalid_item_files": invalid[:20],
        "invalid_item_file_count": len(invalid),
        "connectivity_review": review_details,
        "registered_connectivity_review_item_ids": matching,
        "note": "An inbox file is not registered until ArkaonMailbox.sync_from_inbox is invoked.",
    }


if __name__ == "__main__":
    print(json.dumps(audit(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
