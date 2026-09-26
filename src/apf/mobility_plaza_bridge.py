"""Bridge plaza governance reports into eternian-review inbox packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .mobility_plaza_governance import GovernanceStatus, PlazaGovernanceReport

SCHEMA_PLAZA_INBOX = "apf.plaza-governance-inbox/v1"


def build_plaza_governance_inbox_document(
    *,
    packet_id: str,
    report: PlazaGovernanceReport,
    created_at: datetime,
) -> dict[str, object]:
    summary = (
        f"{report.platform_id}: mobility plaza governance {report.overall.value}; "
        f"{len(report.findings)} finding(s); eternian review required before ops change"
    )
    return {
        "schema_version": SCHEMA_PLAZA_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.ETHERNIAN_REVIEW.value,
        "platform_id": report.platform_id,
        "overall": report.overall.value,
        "report_digest": report.report_digest,
        "finding_count": len(report.findings),
        "summary": summary,
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def write_plaza_governance_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage != InboxStage.ETHERNIAN_REVIEW:
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", "plaza governance requires eternian review")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "plaza governance packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_plaza_governance_report(
    *,
    foundry_root: Path,
    report: PlazaGovernanceReport,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> str | None:
    if report.overall is GovernanceStatus.PASS and not report.findings:
        return None
    packet_id = f"{run_id}-{report.platform_id}-plaza-gov"
    document = build_plaza_governance_inbox_document(packet_id=packet_id, report=report, created_at=now)
    path = write_plaza_governance_packet(foundry_root=foundry_root, document=document, dry_run=dry_run)
    state_dir = foundry_root / "state" / "plaza-governance"
    if not dry_run:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / f"{report.platform_id}-{report.report_digest[:16]}.json").write_text(
            json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return path
