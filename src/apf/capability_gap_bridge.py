"""Bridge capability gap reports into inbox action-request packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .capability_gap import CapabilityGapPolicy, CapabilityGapReport, GapSeverity
from .central_orchestrator import InboxStage, OrchestratorError

SCHEMA_CAPABILITY_GAP_INBOX = "apf.capability-gap-inbox/v1"


def build_capability_gap_inbox_document(
    *,
    packet_id: str,
    report: CapabilityGapReport,
    created_at: datetime,
    inbox_stage: InboxStage,
) -> dict[str, object]:
    gaps = [item.to_document() for item in report.gaps]
    summary_lines = [item.user_message for item in report.gaps[:5]]
    summary = (
        f"{report.owned_platform_id}: ARKAON detected {len(report.gaps)} capability gap(s) vs external platforms; "
        + " ".join(summary_lines)
        + "; action requests only — no auto-implementation"
    )
    return {
        "schema_version": SCHEMA_CAPABILITY_GAP_INBOX,
        "packet_id": packet_id,
        "stage": inbox_stage.value,
        "platform_id": report.owned_platform_id,
        "report_digest": report.report_digest,
        "gap_count": len(report.gaps),
        "gaps": gaps,
        "summary": summary,
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "created_at": created_at.isoformat(),
    }


def write_capability_gap_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise OrchestratorError("INBOX_FORBIDDEN", "capability gap packets must remain request-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_capability_gap_report(
    *,
    foundry_root: Path,
    report: CapabilityGapReport,
    policy: CapabilityGapPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> list[str]:
    if len(report.gaps) < policy.minimum_gaps_for_packet:
        return []
    paths: list[str] = []
    high = [gap for gap in report.gaps if gap.severity is GapSeverity.HIGH]
    if policy.emit_eternian_packet and high:
        document = build_capability_gap_inbox_document(
            packet_id=f"{run_id}-{report.owned_platform_id}-capability-gap-eternian",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.ETHERNIAN_REVIEW,
        )
        document["gaps"] = [item.to_document() for item in high]
        document["gap_count"] = len(high)
        paths.append(write_capability_gap_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    if policy.emit_research_packet:
        document = build_capability_gap_inbox_document(
            packet_id=f"{run_id}-{report.owned_platform_id}-capability-gap-research",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.RESEARCH,
        )
        paths.append(write_capability_gap_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    if report.gaps:
        operator_gaps = report.gaps[:3]
        document = build_capability_gap_inbox_document(
            packet_id=f"{run_id}-{report.owned_platform_id}-capability-gap-operator",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.OPERATOR_DECISION,
        )
        document["gaps"] = [item.to_document() for item in operator_gaps]
        document["gap_count"] = len(operator_gaps)
        document["summary"] = (
            f"{report.owned_platform_id}: operator priority for top capability gaps; "
            + "; ".join(item.user_message for item in operator_gaps)
        )
        paths.append(write_capability_gap_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    return paths
