"""Bridge asset investigation reports into research inbox packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .asset_investigation import AssetInvestigationPolicy, AssetInvestigationReport
from .central_orchestrator import InboxStage, OrchestratorError

SCHEMA_ASSET_INVESTIGATION_INBOX = "apf.asset-investigation-inbox/v1"


def build_asset_investigation_inbox_document(
    *,
    packet_id: str,
    report: AssetInvestigationReport,
    created_at: datetime,
) -> dict[str, object]:
    top = report.priorities[:5]
    lines = [f"{item.rank}. [{item.kind.value}] {item.asset_id} (score={item.score})" for item in top]
    summary = (
        "ARKAON asset investigation ranked best-next assets; "
        + ("; ".join(lines) if lines else "no priorities above threshold")
        + "; research packet only"
    )
    return {
        "schema_version": SCHEMA_ASSET_INVESTIGATION_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": "ARKAON_FOUNDRY",
        "report_digest": report.report_digest,
        "priority_count": len(report.priorities),
        "top_priorities": [item.to_document() for item in top],
        "summary": summary,
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def write_asset_investigation_packet(
    *, foundry_root: Path, document: dict[str, object], dry_run: bool
) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage != InboxStage.RESEARCH:
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", "asset investigation belongs in research inbox")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "asset investigation packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_asset_investigation_report(
    *,
    foundry_root: Path,
    report: AssetInvestigationReport,
    policy: AssetInvestigationPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> str | None:
    if not policy.emit_research_packet:
        return None
    if not report.priorities:
        return None
    if report.priorities[0].score < policy.minimum_score_for_packet:
        return None
    packet_id = f"{run_id}-asset-investigation"
    document = build_asset_investigation_inbox_document(
        packet_id=packet_id,
        report=report,
        created_at=now,
    )
    return write_asset_investigation_packet(foundry_root=foundry_root, document=document, dry_run=dry_run)
