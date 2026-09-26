"""Bridge SNS trend reports and market pioneering proposals into inbox."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .sns_trend_analysis import MarketPioneeringProposal, SNSTrendReport

SCHEMA_SNS_TREND_INBOX = "apf.sns-trend-inbox/v1"


def build_sns_trend_inbox_document(
    *,
    packet_id: str,
    report: SNSTrendReport,
    created_at: datetime,
) -> dict[str, object]:
    summary = (
        f"SNS trend analysis: {len(report.surge_items)} surge item(s), "
        f"{len(report.proposals)} market proposal(s); research packet only"
    )
    return {
        "schema_version": SCHEMA_SNS_TREND_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": "ARKAON_FOUNDRY",
        "summary": summary,
        "report_digest": report.report_digest,
        "surge_count": len(report.surge_items),
        "proposal_count": len(report.proposals),
        "surge_items": [item.to_document() for item in report.surge_items],
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def build_market_proposal_inbox_document(
    *,
    packet_id: str,
    proposal: MarketPioneeringProposal,
    created_at: datetime,
) -> dict[str, object]:
    return {
        **proposal.to_document(),
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "summary": proposal.user_message,
        "created_at": created_at.isoformat(),
    }


def _write_inbox(foundry_root: Path, document: dict[str, object], *, dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "sns trend packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_sns_trend_report(
    *,
    foundry_root: Path,
    report: SNSTrendReport,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> tuple[str, ...]:
    if not report.surge_items:
        return ()
    paths: list[str] = []
    trend_packet_id = f"{run_id}-sns-trend-analysis"
    paths.append(
        _write_inbox(
            foundry_root,
            build_sns_trend_inbox_document(packet_id=trend_packet_id, report=report, created_at=now),
            dry_run=dry_run,
        )
    )
    for proposal in report.proposals:
        packet_id = f"{run_id}-sns-market-{proposal.item_id}"
        paths.append(
            _write_inbox(
                foundry_root,
                build_market_proposal_inbox_document(packet_id=packet_id, proposal=proposal, created_at=now),
                dry_run=dry_run,
            )
        )
    return tuple(paths)
