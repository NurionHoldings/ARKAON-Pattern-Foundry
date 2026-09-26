"""Bridge research watch events into inbox/research packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .research_watch import WatchEvent

SCHEMA_RESEARCH_WATCH_INBOX = "apf.research-watch-inbox/v1"


class ResearchWatchBridgeRejected(ValueError):
    pass


def build_research_watch_inbox_document(
    *,
    packet_id: str,
    event: WatchEvent,
    created_at: datetime,
) -> dict[str, object]:
    change_label = "initial baseline" if event.previous_digest is None else "digest changed"
    summary = (
        f"{event.platform_id}: research watch {event.watch_id} — {change_label}; "
        f"current_digest={event.current_digest[:16]}…; research packet only"
    )
    return {
        "schema_version": SCHEMA_RESEARCH_WATCH_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": event.platform_id,
        "watch_id": event.watch_id,
        "previous_digest": event.previous_digest,
        "current_digest": event.current_digest,
        "changed": event.changed,
        "summary": summary,
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def write_research_watch_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage != InboxStage.RESEARCH:
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", "research watch packets belong in research inbox")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "research watch packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_research_watch_events(
    *,
    foundry_root: Path,
    events: tuple[WatchEvent, ...],
    run_id: str,
    now: datetime,
    dry_run: bool,
    emit_unchanged: bool = False,
) -> tuple[str, ...]:
    paths: list[str] = []
    for event in events:
        if not emit_unchanged and event.previous_digest is not None and not event.changed:
            continue
        packet_id = f"{run_id}-watch-{event.watch_id}"
        document = build_research_watch_inbox_document(packet_id=packet_id, event=event, created_at=now)
        paths.append(write_research_watch_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    return tuple(paths)
