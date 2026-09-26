"""Bridge cross-platform learning into eternian-review lesson seed packets."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .cross_platform_learning import CrossPlatformLearningPolicy, CrossPlatformLearningReport
from .reflective_learning import (
    ArkaonReflectiveLearning,
    ExternalObservation,
    Metric,
    ReflectionStage,
    SelfAssessment,
)

SCHEMA_CROSS_PLATFORM_LESSON_INBOX = "apf.cross-platform-lesson-inbox/v1"


def _seed_reflection_case(*, report: CrossPlatformLearningReport, seed) -> None:
    learning = ArkaonReflectiveLearning()
    learning.observe(
        seed.case_id,
        ExternalObservation(
            observation_id=f"obs-{seed.case_id}",
            source_evidence_digest=seed.evidence_digest,
            source_feature=seed.reusable_pattern,
            problem_solved="cross-platform structural pattern alignment",
            observed_method=seed.principle,
            official_verified=True,
            copy_prohibited=True,
        ),
    )
    learning.assess_self(
        seed.case_id,
        SelfAssessment(
            platform_id=seed.platform_scope,
            current_capability="partial landing structural coverage",
            strength="external observation digests available",
            gap=f"missing reusable {seed.reusable_pattern}",
            root_cause="incomplete cross-platform compare cycle",
            user_impact="conversion funnel patterns not yet abstracted",
            policy_conflicts=("verbatim copy prohibited", "auto-promotion prohibited"),
        ),
    )
    learning.propose_hypothesis(
        seed.case_id,
        hypothesis=f"{seed.reusable_pattern} is reusable as clean-room landing structure",
        synthetic_test_plan=("structural route consistency check", "contamination gate"),
    )
    learning.record_shadow(
        seed.case_id,
        (Metric("cross_platform_coverage", 0.3, 0.7, True),),
    )


def build_cross_platform_lesson_inbox_document(
    *,
    packet_id: str,
    report: CrossPlatformLearningReport,
    seed,
    created_at: datetime,
) -> dict[str, object]:
    summary = (
        f"{report.source_platform_id}: cross-platform lesson seed for {seed.reusable_pattern}; "
        f"pattern {seed.pattern_id}; eternian review before operator decision and immutable lesson"
    )
    return {
        "schema_version": SCHEMA_CROSS_PLATFORM_LESSON_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.ETHERNIAN_REVIEW.value,
        "platform_id": report.source_platform_id,
        "packet_kind": "CROSS_PLATFORM_LESSON_SEED",
        "case_id": seed.case_id,
        "reflection_stage": ReflectionStage.SYNTHETIC_SHADOWED.value,
        "report_digest": report.report_digest,
        "pattern_proposals": [item.to_document() for item in report.pattern_proposals],
        "lesson_seed": seed.to_document(),
        "summary": summary,
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "created_at": created_at.isoformat(),
    }


def write_cross_platform_lesson_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise OrchestratorError("INBOX_FORBIDDEN", "cross-platform lesson packets must remain propose-only")
    target = foundry_root / "inbox" / "eternian-review" / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_cross_platform_learning_report(
    *,
    foundry_root: Path,
    report: CrossPlatformLearningReport,
    policy: CrossPlatformLearningPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> list[str]:
    if not report.lesson_seeds or not policy.emit_eternian_lesson_packet:
        return []
    paths: list[str] = []
    for index, seed in enumerate(report.lesson_seeds):
        if not dry_run:
            _seed_reflection_case(report=report, seed=seed)
        packet_id = f"{run_id}-xplat-lesson-{index}-{sha256(seed.case_id.encode()).hexdigest()[:8]}"
        document = build_cross_platform_lesson_inbox_document(
            packet_id=packet_id,
            report=report,
            seed=seed,
            created_at=now,
        )
        paths.append(write_cross_platform_lesson_packet(foundry_root=foundry_root, document=document, dry_run=dry_run))
    return paths
