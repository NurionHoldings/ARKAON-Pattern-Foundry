"""Bridge learning impediment reports into inbox modification-request packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .learning_impediment import (
    ImpedimentSeverity,
    LearningImpedimentPolicy,
    LearningImpedimentReport,
    ModificationRequest,
    ModificationTarget,
)

SCHEMA_LEARNING_IMPEDIMENT_INBOX = "apf.learning-impediment-inbox/v1"


def _report_summary(report: LearningImpedimentReport, *, prefix: str) -> str:
    by_category: dict[str, int] = {}
    for item in report.impediments:
        by_category[item.category.value] = by_category.get(item.category.value, 0) + 1
    parts = [f"{key}={value}" for key, value in sorted(by_category.items())]
    category_text = ", ".join(parts) if parts else "none"
    return (
        f"{prefix}: {len(report.impediments)} item(s) "
        f"(self-limit / storage / improvement-program: {category_text}); "
        "modification requests for eternian/beom — no auto-fix"
    )


def build_learning_impediment_inbox_document(
    *,
    packet_id: str,
    report: LearningImpedimentReport,
    created_at: datetime,
    inbox_stage: InboxStage,
    impediments: tuple,
    modification_requests: tuple[ModificationRequest, ...],
    summary: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_LEARNING_IMPEDIMENT_INBOX,
        "packet_id": packet_id,
        "stage": inbox_stage.value,
        "platform_id": "ARKAON_FOUNDRY",
        "packet_kind": "LEARNING_MODIFICATION_REQUEST",
        "report_digest": report.report_digest,
        "impediment_count": len(impediments),
        "impediments": [item.to_document() for item in impediments],
        "modification_requests": [item.to_document() for item in modification_requests],
        "summary": summary,
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "created_at": created_at.isoformat(),
    }


def write_learning_impediment_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise OrchestratorError("INBOX_FORBIDDEN", "learning impediment packets must remain request-only")
    stage = InboxStage(str(document["stage"]))
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def _requests_for_target(
    report: LearningImpedimentReport,
    target: ModificationTarget,
) -> tuple[ModificationRequest, ...]:
    rows: list[ModificationRequest] = []
    seen: set[str] = set()
    for impediment in report.impediments:
        for request in impediment.modification_requests:
            if request.target is not target:
                continue
            if request.request_id in seen:
                continue
            seen.add(request.request_id)
            rows.append(request)
    return tuple(rows)


def bridge_learning_impediment_report(
    *,
    foundry_root: Path,
    report: LearningImpedimentReport,
    policy: LearningImpedimentPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> list[str]:
    if len(report.impediments) < policy.minimum_impediments_for_packet:
        return []
    paths: list[str] = []
    if policy.emit_research_packet:
        document = build_learning_impediment_inbox_document(
            packet_id=f"{run_id}-learning-impediment-research",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.RESEARCH,
            impediments=report.impediments,
            modification_requests=tuple(
                request
                for impediment in report.impediments
                for request in impediment.modification_requests
            ),
            summary=_report_summary(report, prefix="ARKAON learning impediment scan"),
        )
        paths.append(write_learning_impediment_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))

    eternian_requests = _requests_for_target(report, ModificationTarget.ETERNIAN)
    high_impediments = tuple(item for item in report.impediments if item.severity is ImpedimentSeverity.HIGH)
    if policy.emit_eternian_packet and eternian_requests:
        document = build_learning_impediment_inbox_document(
            packet_id=f"{run_id}-learning-impediment-eternian",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.ETHERNIAN_REVIEW,
            impediments=high_impediments or report.impediments,
            modification_requests=eternian_requests,
            summary=(
                "에테르니언 검토: 학습을 방해하는 아르카온 기능·정책 제한에 대한 수정 승인 요청 — "
                + "; ".join(item.modification_summary for item in eternian_requests[:3])
            ),
        )
        paths.append(write_learning_impediment_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))

    beom_requests = _requests_for_target(report, ModificationTarget.BEOM)
    if policy.emit_beom_packet and beom_requests:
        document = build_learning_impediment_inbox_document(
            packet_id=f"{run_id}-learning-impediment-beom",
            report=report,
            created_at=now,
            inbox_stage=InboxStage.OPERATOR_DECISION,
            impediments=report.impediments[:5],
            modification_requests=beom_requests,
            summary=(
                "범(운영자) 결정: 학습 방해 self-limit 완화·설정 수정 요청 — "
                + "; ".join(item.modification_summary for item in beom_requests[:3])
            ),
        )
        paths.append(write_learning_impediment_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    return paths
