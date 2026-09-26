"""Bridge map ops gate reports into eternian-review inbox packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .map_ops_gate import GateStatus, MapOpsGateReport

SCHEMA_MAP_OPS_INBOX = "apf.map-ops-gate-inbox/v1"


def build_map_ops_inbox_document(
    *,
    packet_id: str,
    report: MapOpsGateReport,
    created_at: datetime,
) -> dict[str, object]:
    failed = sum(1 for item in report.results if item.status is GateStatus.FAIL)
    advisory = sum(1 for item in report.results if item.status is GateStatus.ADVISORY)
    summary = (
        f"{report.platform_id}: map ops gates {report.overall.value}; "
        f"{failed} fail, {advisory} advisory; eternian review required before map activation"
    )
    return {
        "schema_version": SCHEMA_MAP_OPS_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.ETHERNIAN_REVIEW.value,
        "platform_id": report.platform_id,
        "overall": report.overall.value,
        "report_digest": report.report_digest,
        "gate_count": len(report.results),
        "summary": summary,
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def write_map_ops_inbox_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage != InboxStage.ETHERNIAN_REVIEW:
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", "map ops gate requires eternian review")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "map ops packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_map_ops_gate_report(
    *,
    foundry_root: Path,
    report: MapOpsGateReport,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> str | None:
    if report.overall is GateStatus.PASS:
        return None
    packet_id = f"{run_id}-{report.platform_id}-map-ops"
    document = build_map_ops_inbox_document(packet_id=packet_id, report=report, created_at=now)
    path = write_map_ops_inbox_packet(foundry_root=foundry_root, document=document, dry_run=dry_run)
    state_dir = foundry_root / "state" / "map-ops-gate"
    if not dry_run:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / f"{report.platform_id}-{report.report_digest[:16]}.json").write_text(
            json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return path
