"""Bridge SNS attention-factor assets into inbox research packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .sns_attention_analysis import AttentionProductionAsset, SNSAttentionReport

SCHEMA_SNS_ATTENTION_INBOX = "apf.sns-attention-inbox/v1"


def build_attention_summary_inbox_document(
    *,
    packet_id: str,
    report: SNSAttentionReport,
    created_at: datetime,
) -> dict[str, object]:
    top_driver = report.driver_rankings[0][0] if report.driver_rankings else None
    summary = (
        f"SNS attention-factor analysis: {len(report.assets)} production asset(s); "
        f"top driver '{top_driver}'; research packet only"
    )
    return {
        "schema_version": SCHEMA_SNS_ATTENTION_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": "ARKAON_FOUNDRY",
        "summary": summary,
        "report_digest": report.report_digest,
        "asset_count": len(report.assets),
        "driver_rankings": [{"driver": driver, "count": count} for driver, count in report.driver_rankings],
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def build_attention_asset_inbox_document(
    *,
    packet_id: str,
    asset: AttentionProductionAsset,
    created_at: datetime,
) -> dict[str, object]:
    return {
        **asset.to_document(),
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "summary": asset.production_guidance,
        "packet_kind": "SHORTS_PRODUCTION_ASSET",
        "created_at": created_at.isoformat(),
    }


def _write_inbox(foundry_root: Path, document: dict[str, object], *, dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "sns attention packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_sns_attention_report(
    *,
    foundry_root: Path,
    report: SNSAttentionReport,
    run_id: str,
    now: datetime,
    dry_run: bool,
    emit_inbox_packets: bool = True,
) -> tuple[str, ...]:
    if not report.assets or not emit_inbox_packets:
        return ()
    paths: list[str] = []
    summary_id = f"{run_id}-sns-attention-analysis"
    paths.append(
        _write_inbox(
            foundry_root,
            build_attention_summary_inbox_document(packet_id=summary_id, report=report, created_at=now),
            dry_run=dry_run,
        )
    )
    for asset in report.assets:
        packet_id = f"{run_id}-sns-attention-{asset.item_id}"
        paths.append(
            _write_inbox(
                foundry_root,
                build_attention_asset_inbox_document(packet_id=packet_id, asset=asset, created_at=now),
                dry_run=dry_run,
            )
        )
    return tuple(paths)
