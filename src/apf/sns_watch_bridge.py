"""Bridge SNS watch events into inbox/research packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .sns_watch import SNSChangeKind, SNSEvent

SCHEMA_SNS_WATCH_INBOX = "apf.sns-watch-inbox/v1"

_CHANGE_LABELS = {
    SNSChangeKind.BASELINE: "SNS baseline established",
    SNSChangeKind.FEATURE_CHANGE: "new/changed SNS feature signal",
    SNSChangeKind.ENVIRONMENT_CHANGE: "SNS environment/layout signal changed",
    SNSChangeKind.FORMAT_CHANGE: "SNS content format signal changed",
    SNSChangeKind.SURFACE_CHANGE: "SNS public surface digest changed",
    SNSChangeKind.CLICK_SURGE: "SNS click velocity surge detected",
    SNSChangeKind.TREND_SHIFT: "SNS trend category/shift signal changed",
}


def build_sns_watch_inbox_document(
    *,
    packet_id: str,
    event: SNSEvent,
    created_at: datetime,
) -> dict[str, object]:
    label = _CHANGE_LABELS.get(event.change_kind, "SNS structural change")
    summary = (
        f"{event.platform_id}: sns watch {event.watch_id} — {label}; "
        f"change={event.change_kind.value}; digest={event.current_digest[:16]}…; research packet only"
    )
    return {
        "schema_version": SCHEMA_SNS_WATCH_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": event.platform_id,
        "watch_id": event.watch_id,
        "source_kind": event.source_kind.value,
        "change_kind": event.change_kind.value,
        "previous_digest": event.previous_digest,
        "current_digest": event.current_digest,
        "signal_delta": event.signal_delta,
        "domain_ids": list(event.domain_ids),
        "summary": summary,
        "production_change_allowed": False,
        "automatic_learning": False,
        "verbatim_post_storage": False,
        "created_at": created_at.isoformat(),
    }


def write_sns_watch_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage != InboxStage.RESEARCH:
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", "sns watch packets belong in research inbox")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "sns watch packets must remain propose-only")
    if document.get("verbatim_post_storage"):
        raise OrchestratorError("INBOX_FORBIDDEN", "sns watch packets must not store verbatim posts")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_sns_watch_events(
    *,
    foundry_root: Path,
    events: tuple[SNSEvent, ...],
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> tuple[str, ...]:
    paths: list[str] = []
    for event in events:
        packet_id = f"{run_id}-sns-{event.watch_id}"
        document = build_sns_watch_inbox_document(packet_id=packet_id, event=event, created_at=now)
        paths.append(write_sns_watch_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    return tuple(paths)
