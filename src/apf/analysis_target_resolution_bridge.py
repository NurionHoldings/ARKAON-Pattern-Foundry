"""Bridge analysis target resolution reports into inbox research packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .analysis_target_resolution import AnalysisTargetResolutionPolicy, AnalysisTargetResolutionReport
from .central_orchestrator import InboxStage, OrchestratorError

SCHEMA_ANALYSIS_TARGET_RESOLUTION_INBOX = "apf.analysis-target-resolution-inbox/v1"


def build_analysis_target_resolution_inbox_document(
    *,
    packet_id: str,
    report: AnalysisTargetResolutionReport,
    created_at: datetime,
) -> dict[str, object]:
    summaries = [item.rationale for item in report.targets[:3]]
    summary = (
        f"ARKAON: ambiguous target ({report.ambiguity_reason}); "
        f"continue cross-platform analysis from last user site "
        f"{report.last_user_site.platform_id if report.last_user_site else 'unknown'} — "
        + "; ".join(summaries)
        + "; research only — no auto-implementation"
    )
    return {
        "schema_version": SCHEMA_ANALYSIS_TARGET_RESOLUTION_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": report.last_user_site.platform_id if report.last_user_site else "ARKAON_FOUNDRY",
        "packet_kind": "CROSS_PLATFORM_ANALYSIS_CONTINUATION",
        "report_digest": report.report_digest,
        "ambiguous": report.ambiguous,
        "ambiguity_reason": report.ambiguity_reason,
        "last_user_site": report.last_user_site.to_document() if report.last_user_site else None,
        "targets": [item.to_document() for item in report.targets],
        "summary": summary,
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "created_at": created_at.isoformat(),
    }


def write_analysis_target_resolution_packet(
    *, foundry_root: Path, document: dict[str, object], dry_run: bool
) -> str:
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise OrchestratorError(
            "INBOX_FORBIDDEN", "analysis target resolution packets must remain request-only"
        )
    target = foundry_root / "inbox" / "research" / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_analysis_target_resolution_report(
    *,
    foundry_root: Path,
    report: AnalysisTargetResolutionReport,
    policy: AnalysisTargetResolutionPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> list[str]:
    if not report.ambiguous or not report.targets or not policy.emit_research_packet:
        return []
    document = build_analysis_target_resolution_inbox_document(
        packet_id=f"{run_id}-cross-platform-analysis",
        report=report,
        created_at=now,
    )
    return [write_analysis_target_resolution_packet(foundry_root=foundry_root, document=document, dry_run=dry_run)]
