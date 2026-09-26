"""Bridge public surface observations into research inbox and reflective learning seeds."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .public_surface_observer import SurfaceObservationReport
from .reflective_learning import (
    ArkaonReflectiveLearning,
    ExternalObservation,
    Metric,
    SelfAssessment,
)
from .static_js_normalizer import NormalizedJsStructure

SCHEMA_SURFACE_INBOX = "apf.public-surface-inbox/v1"


class PublicSurfaceBridgeRejected(ValueError):
    pass


def build_surface_inbox_document(
    *,
    packet_id: str,
    report: SurfaceObservationReport,
    created_at: datetime,
) -> dict[str, object]:
    js_count = len(report.js_structures)
    route_count = len(report.openapi_paths) + len(report.policy_route_refs)
    summary = (
        f"{report.platform_id}: public surface observation — "
        f"{route_count} route refs, {js_count} normalized JS structures; "
        f"copy prohibited, structural digest only"
    )
    return {
        "schema_version": SCHEMA_SURFACE_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.RESEARCH.value,
        "platform_id": report.platform_id,
        "observation_digest": report.observation_digest,
        "rights_posture": report.rights_posture,
        "summary": summary,
        "js_structure_count": js_count,
        "route_ref_count": route_count,
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def write_surface_inbox_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage != InboxStage.RESEARCH:
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", "public surface observations belong in research inbox")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "surface inbox packets must remain propose-only")
    target = foundry_root / "inbox" / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def seed_reflective_observation_from_surface(
    learning: ArkaonReflectiveLearning,
    *,
    case_id: str,
    report: SurfaceObservationReport,
    top_structure: NormalizedJsStructure | None,
) -> None:
    feature = "공개 surface route·정책·JS 구조"
    method = "parser-only normalization and structural digest"
    if top_structure is not None:
        feature = f"JS structure {top_structure.source_path}"
        method = "; ".join(top_structure.deobfuscated_preview_lines)
    learning.observe(
        case_id,
        ExternalObservation(
            observation_id=f"surface-{report.observation_digest[:12]}",
            source_evidence_digest=report.observation_digest,
            source_feature=feature,
            problem_solved="경쟁사 복제 없이 개선점 관찰",
            observed_method=method,
            official_verified=True,
            copy_prohibited=True,
        ),
    )


def bridge_public_surface_observation(
    *,
    foundry_root: Path,
    report: SurfaceObservationReport,
    run_id: str,
    now: datetime,
    dry_run: bool,
    seed_reflective: bool = False,
) -> tuple[str, str | None]:
    packet_id = f"{run_id}-{report.platform_id}-surface"
    document = build_surface_inbox_document(packet_id=packet_id, report=report, created_at=now)
    inbox_path = write_surface_inbox_packet(foundry_root=foundry_root, document=document, dry_run=dry_run)
    case_id: str | None = None
    if seed_reflective and report.js_structures:
        learning = ArkaonReflectiveLearning()
        case_id = f"surface-{report.platform_id}-{report.observation_digest[:12]}"
        seed_reflective_observation_from_surface(
            learning,
            case_id=case_id,
            report=report,
            top_structure=report.js_structures[0],
        )
        learning.assess_self(
            case_id,
            SelfAssessment(
                report.platform_id,
                "공개 surface 관측",
                "route·정책·구조 digest 확보",
                "minified JS 내부 구조 가시성 부족",
                "관찰 파이프라인 미연결",
                "개선점 발견 지연",
                ("자동복제 금지",),
            ),
        )
        learning.propose_hypothesis(
            case_id,
            hypothesis="구조 digest 기반 개선 제안을 분리한다",
            synthetic_test_plan=("합성 route 정합성", "JS structure diff"),
        )
        learning.record_shadow(
            case_id,
            (Metric("structure_coverage", 0.4, 0.75, True),),
        )
    state_dir = foundry_root / "state" / "surface-observations"
    if not dry_run:
        state_dir.mkdir(parents=True, exist_ok=True)
        digest_doc = report.to_document()
        digest_doc.pop("visible_text_samples", None)
        (state_dir / f"{report.platform_id}-{report.observation_digest[:16]}.json").write_text(
            json.dumps(digest_doc, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return inbox_path, case_id


def surface_observation_digest(report: SurfaceObservationReport) -> str:
    return report.observation_digest
