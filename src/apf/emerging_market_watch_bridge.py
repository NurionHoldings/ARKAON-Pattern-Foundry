"""Bridge emerging market events into inbox/research packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .emerging_market_watch import EmergingMarketEvent, MarketChangeKind

SCHEMA_EMERGING_MARKET_INBOX = "apf.emerging-market-inbox/v1"

_LABELS = {
    MarketChangeKind.BASELINE: "emerging market baseline",
    MarketChangeKind.NEW_MARKET_SEGMENT: "new market segment signal",
    MarketChangeKind.DEMAND_SHIFT: "demand shift signal",
    MarketChangeKind.REGULATORY_SIGNAL: "regulatory/market rule signal",
    MarketChangeKind.NOVELTY_RISE: "novelty or change velocity rise",
    MarketChangeKind.MARKET_SURFACE_CHANGE: "market index surface changed",
}


def build_emerging_market_inbox_document(
    *,
    packet_id: str,
    event: EmergingMarketEvent,
    created_at: datetime,
) -> dict[str, object]:
    label = _LABELS.get(event.change_kind, "market change")
    summary = (
        f"{event.platform_id}: emerging market {event.watch_id} ({event.market_scope}) — {label}; "
        f"change={event.change_kind.value}; digest={event.current_digest[:16]}…; research packet only"
    )
    return {
        "schema_version": SCHEMA_EMERGING_MARKET_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": event.platform_id,
        "watch_id": event.watch_id,
        "market_scope": event.market_scope,
        "source_kind": event.source_kind.value,
        "change_kind": event.change_kind.value,
        "previous_digest": event.previous_digest,
        "current_digest": event.current_digest,
        "signal_delta": event.signal_delta,
        "summary": summary,
        "production_change_allowed": False,
        "automatic_learning": False,
        "verbatim_storage": False,
        "created_at": created_at.isoformat(),
    }


def write_emerging_market_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage != InboxStage.RESEARCH:
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", "emerging market packets belong in research inbox")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "emerging market packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_emerging_market_events(
    *,
    foundry_root: Path,
    events: tuple[EmergingMarketEvent, ...],
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> tuple[str, ...]:
    paths: list[str] = []
    for event in events:
        packet_id = f"{run_id}-market-{event.watch_id}"
        document = build_emerging_market_inbox_document(packet_id=packet_id, event=event, created_at=now)
        paths.append(write_emerging_market_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    return tuple(paths)
