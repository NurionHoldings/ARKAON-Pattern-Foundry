"""Bridge experience audit findings into reflective learning and governed inbox packets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .admin_change_control import AdminChangeController, ChangeControlRejected, ChangeScope
from .central_orchestrator import InboxStage, OrchestratorError
from .experience_operations_audit import ImprovementProposal
from .reflective_learning import (
    ArkaonReflectiveLearning,
    Decision,
    ExternalObservation,
    Metric,
    ReflectionStage,
    SelfAssessment,
)
from .reflective_lesson_store import ReflectiveLessonStore

SCHEMA_REFLECTION_INBOX = "apf.reflection-bridge-inbox/v1"
_FORBIDDEN_KNOWLEDGE_KEYS = frozenset(
    {"member", "order", "location", "settlement", "contract_body", "identity", "pii", "credential", "secret"}
)


class ReflectionBridgeRejected(ValueError):
    pass


@dataclass(frozen=True)
class ReflectionBridgePolicy:
    automatic_operational_application: bool = False
    self_approval: bool = False
    automatic_merge_or_deploy: bool = False

    @classmethod
    def load(cls, path: Path) -> ReflectionBridgePolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-reflective-learning.v1":
            raise ReflectionBridgeRejected("unsupported reflective learning policy schema")
        if (
            document.get("automatic_operational_application")
            or document.get("self_approval")
            or document.get("automatic_merge_or_deploy")
        ):
            raise ReflectionBridgeRejected("reflection bridge must remain propose-only")
        return cls(
            automatic_operational_application=bool(document.get("automatic_operational_application")),
            self_approval=bool(document.get("self_approval")),
            automatic_merge_or_deploy=bool(document.get("automatic_merge_or_deploy")),
        )


def case_id_for_proposal(proposal: ImprovementProposal) -> str:
    return f"refl-{proposal.platform_id}-{proposal.finding.finding_id}"


def proposal_id_for_case(case_id: str) -> str:
    return f"change-{case_id}"


def seed_reflective_case(
    learning: ArkaonReflectiveLearning,
    proposal: ImprovementProposal,
) -> str:
    case_id = case_id_for_proposal(proposal)
    observation = ExternalObservation(
        observation_id=f"obs-{proposal.finding.finding_id}",
        source_evidence_digest=proposal.evidence_digest,
        source_feature=proposal.finding.title,
        problem_solved=proposal.user_impact or proposal.finding.title,
        observed_method=proposal.recommendation,
        official_verified=True,
        copy_prohibited=True,
    )
    learning.observe(case_id, observation)
    learning.assess_self(
        case_id,
        SelfAssessment(
            platform_id=proposal.platform_id,
            current_capability="현재 구현 상태",
            strength="공개 구조 분석 가능",
            gap=proposal.finding.title,
            root_cause=proposal.finding.category,
            user_impact=proposal.user_impact or proposal.finding.title,
            policy_conflicts=("자동반영 금지",),
        ),
    )
    learning.propose_hypothesis(
        case_id,
        hypothesis=proposal.recommendation,
        synthetic_test_plan=proposal.required_synthetic_tests or ("합성 정합성 시험",),
    )
    baseline = 0.5
    candidate = 0.8 if proposal.finding.severity.value in {"BLOCKER", "HIGH"} else 0.7
    learning.record_shadow(
        case_id,
        (Metric("proposal_confidence", baseline, candidate, True),),
    )
    return case_id


def build_reflection_inbox_document(
    *,
    packet_id: str,
    stage: InboxStage,
    platform_id: str,
    case_id: str,
    proposal: ImprovementProposal,
    reflection_stage: ReflectionStage,
    created_at: datetime,
) -> dict[str, object]:
    summary = (
        f"{platform_id}: reflection bridge case {case_id} at {reflection_stage.value}; "
        f"{proposal.finding.title}; eternian review required before operator decision"
    )
    for key in _FORBIDDEN_KNOWLEDGE_KEYS:
        if key in summary.casefold():
            raise ReflectionBridgeRejected("summary touched forbidden operational category")
    return {
        "schema_version": SCHEMA_REFLECTION_INBOX,
        "packet_id": packet_id,
        "stage": stage.value,
        "platform_id": platform_id,
        "case_id": case_id,
        "proposal_id": proposal_id_for_case(case_id),
        "reflection_stage": reflection_stage.value,
        "finding_id": proposal.finding.finding_id,
        "proposal_digest": proposal.proposal_digest,
        "evidence_digest": proposal.evidence_digest,
        "summary": summary,
        "production_change_allowed": False,
        "automatic_learning": False,
        "created_at": created_at.isoformat(),
    }


def write_reflection_inbox_packet(
    *,
    foundry_root: Path,
    document: dict[str, object],
    dry_run: bool,
) -> str:
    stage = InboxStage(str(document["stage"]))
    if stage == InboxStage.OPERATOR_DECISION:
        raise OrchestratorError(
            "INBOX_STAGE_FORBIDDEN",
            "operator-decision requires eternian review first",
        )
    if stage not in (InboxStage.RESEARCH, InboxStage.ETHERNIAN_REVIEW):
        raise OrchestratorError("INBOX_STAGE_FORBIDDEN", f"unsupported inbox stage: {stage.value}")
    if document.get("production_change_allowed") or document.get("automatic_learning"):
        raise OrchestratorError("INBOX_FORBIDDEN", "reflection inbox packets must remain propose-only")
    inbox_root = foundry_root / "inbox"
    target = inbox_root / stage.value / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def create_change_scopes(proposal: ImprovementProposal) -> tuple[ChangeScope, ...]:
    location = proposal.location or proposal.platform_id
    return (
        ChangeScope(
            scope_id="recommendation",
            label=proposal.finding.title,
            preview_lines=(
                f"affected_path: {location}",
                f"recommendation: {proposal.recommendation}",
                f"impact: {proposal.user_impact}",
            ),
        ),
        ChangeScope(
            scope_id="synthetic-tests",
            label="합성시험 계획",
            preview_lines=tuple(proposal.required_synthetic_tests or ("합성 정합성 시험",)),
        ),
    )


def bridge_experience_proposal(
    *,
    foundry_root: Path,
    proposal: ImprovementProposal,
    run_id: str,
    now: datetime,
    dry_run: bool,
    learning: ArkaonReflectiveLearning | None = None,
    change_controller: AdminChangeController | None = None,
) -> tuple[str, str, str]:
    """Seed reflective case, write eternian-review packet, register change proposal."""
    ReflectionBridgePolicy.load(foundry_root / "config" / "arkaon-reflective-learning-policy.json")
    engine = learning or ArkaonReflectiveLearning()
    controller = change_controller or AdminChangeController(foundry_root=foundry_root)
    case_id = seed_reflective_case(engine, proposal)
    packet_id = f"{run_id}-{case_id}-reflection"
    document = build_reflection_inbox_document(
        packet_id=packet_id,
        stage=InboxStage.ETHERNIAN_REVIEW,
        platform_id=proposal.platform_id,
        case_id=case_id,
        proposal=proposal,
        reflection_stage=ReflectionStage.SYNTHETIC_SHADOWED,
        created_at=now,
    )
    inbox_path = write_reflection_inbox_packet(
        foundry_root=foundry_root,
        document=document,
        dry_run=dry_run,
    )
    change_id = proposal_id_for_case(case_id)
    if not dry_run:
        try:
            controller.create_proposal(
                proposal_id=change_id,
                platform_id=proposal.platform_id,
                case_id=case_id,
                source_digest=proposal.proposal_digest or proposal.evidence_digest,
                summary=document["summary"],
                scopes=create_change_scopes(proposal),
                now=now,
            )
        except ChangeControlRejected as error:
            raise ReflectionBridgeRejected(str(error)) from error
    return case_id, inbox_path, change_id


def bridge_experience_proposals(
    *,
    foundry_root: Path,
    proposals: tuple[ImprovementProposal, ...],
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> tuple[tuple[str, str, str], ...]:
    results: list[tuple[str, str, str]] = []
    learning = ArkaonReflectiveLearning()
    controller = AdminChangeController(foundry_root=foundry_root)
    for proposal in proposals:
        results.append(
            bridge_experience_proposal(
                foundry_root=foundry_root,
                proposal=proposal,
                run_id=run_id,
                now=now,
                dry_run=dry_run,
                learning=learning,
                change_controller=controller,
            )
        )
    return tuple(results)


def promote_to_operator_decision(
    *,
    foundry_root: Path,
    packet_id: str,
    eternian_review_digest: str,
    now: datetime,
    dry_run: bool,
) -> str:
    """Move an eternian-reviewed reflection packet into operator-decision (manual promotion)."""
    if len(eternian_review_digest) != 64:
        raise ReflectionBridgeRejected("eternian review digest required")
    source = foundry_root / "inbox" / InboxStage.ETHERNIAN_REVIEW.value / f"{packet_id}.json"
    if not source.is_file():
        raise ReflectionBridgeRejected("eternian-review packet not found")
    document = json.loads(source.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_REFLECTION_INBOX:
        raise ReflectionBridgeRejected("not a reflection bridge packet")
    updated = {
        **document,
        "stage": InboxStage.OPERATOR_DECISION.value,
        "eternian_review_digest": eternian_review_digest,
        "promoted_at": now.isoformat(),
        "reflection_stage": ReflectionStage.ETERNIAN_REVIEWED.value,
    }
    target = foundry_root / "inbox" / InboxStage.OPERATOR_DECISION.value / f"{packet_id}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def complete_operator_decision_to_lesson(
    *,
    learning: ArkaonReflectiveLearning,
    store: ReflectiveLessonStore,
    case_id: str,
    eternian_review_digest: str,
    decision: Decision,
    decision_digest: str,
    lesson_id: str,
    principle: str,
    reusable_pattern: str,
    failure_or_rejection_reason: str,
    now: datetime,
) -> Path:
    """Close the reflection loop: eternian review → operator decision → immutable lesson."""
    learning.eternian_review(case_id, review_digest=eternian_review_digest)
    learning.operator_decide(case_id, decision=decision, decision_digest=decision_digest)
    lesson = learning.record_lesson(
        case_id,
        lesson_id=lesson_id,
        principle=principle,
        reusable_pattern=reusable_pattern,
        failure_or_rejection_reason=failure_or_rejection_reason,
        now=now,
    )
    return store.append(lesson)
