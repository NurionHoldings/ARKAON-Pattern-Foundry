"""Bridge intent DNA self-repair reports into inbox review packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .intent_dna_self_repair import IntentDnaSelfRepairPolicy, IntentDnaSelfRepairReport

SCHEMA_INTENT_DNA_SELF_REPAIR_INBOX = "apf.intent-dna-self-repair-inbox/v1"


def build_intent_dna_self_repair_inbox_document(
    *,
    packet_id: str,
    report: IntentDnaSelfRepairReport,
    created_at: datetime,
    inbox_stage: InboxStage,
    summary: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_INTENT_DNA_SELF_REPAIR_INBOX,
        "packet_id": packet_id,
        "stage": inbox_stage.value,
        "platform_id": "ARKAON_FOUNDRY",
        "packet_kind": "INTENT_DNA_SELF_REPAIR",
        "report_digest": report.report_digest,
        "missing_count": len(report.missing_features),
        "generated_count": len(report.generated_seeds),
        "missing_features": [item.to_document() for item in report.missing_features[:20]],
        "generated_seeds": [item.to_document() for item in report.generated_seeds[:20]],
        "summary": summary,
        "authorization": {
            "basis": "SELF_DIAGNOSIS_SELF_GENERATION",
            "mutate_locked_intent_dna": False,
        },
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "created_at": created_at.isoformat(),
    }


def write_intent_dna_self_repair_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise OrchestratorError("INBOX_FORBIDDEN", "intent dna self-repair packets must remain propose-only")
    stage = InboxStage(str(document["stage"]))
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_intent_dna_self_repair_report(
    *,
    foundry_root: Path,
    report: IntentDnaSelfRepairReport,
    policy: IntentDnaSelfRepairPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> list[str]:
    if not report.missing_features and not report.generated_seeds:
        return []
    paths: list[str] = []
    if policy.emit_research_packet:
        document = build_intent_dna_self_repair_inbox_document(
            packet_id=f"{run_id}-intent-dna-self-repair-research",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.RESEARCH,
            summary=(
                f"Intent_DNA self-repair: missing={len(report.missing_features)} "
                f"generated_pass0={len(report.generated_seeds)} — no locked DNA mutation"
            ),
        )
        paths.append(write_intent_dna_self_repair_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))

    if policy.emit_eternian_packet and (report.generated_seeds or report.missing_features):
        document = build_intent_dna_self_repair_inbox_document(
            packet_id=f"{run_id}-intent-dna-self-repair-eternian",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.ETHERNIAN_REVIEW,
            summary=(
                "에테르니언 검토: 범/에테르니언 추가 기능의 누락 Intent_DNA — "
                "Pass-0 self-generated seed 승인·CORE lock 여부 결정"
            ),
        )
        paths.append(write_intent_dna_self_repair_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    return paths
