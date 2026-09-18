from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from apf.admin_change_control import AdminChangeController
from apf.central_orchestrator import (
    CentralOrchestrator,
    InboxStage,
    OrchestratorError,
    PlatformRegistration,
)
from apf.experience_operations_audit import (
    FindingSeverity,
    ImprovementFinding,
    ImprovementProposal,
    MaximumOutcome,
)
from apf.reflection_bridge import (
    bridge_experience_proposal,
    case_id_for_proposal,
    complete_operator_decision_to_lesson,
    promote_to_operator_decision,
    seed_reflective_case,
)
from apf.reflective_learning import ArkaonReflectiveLearning, Decision
from apf.reflective_lesson_store import ReflectiveLessonStore

NOW = datetime(2026, 9, 17, tzinfo=UTC)
HEAD = "e2dd9f5d55e5a3a953af565ca467bd0aa4d1c875"
FOUNDRY = Path(__file__).resolve().parents[1]


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def proposal(platform_id: str = "DEMO") -> ImprovementProposal:
    finding = ImprovementFinding(
        finding_id="f1",
        category="ux",
        severity=FindingSeverity.HIGH,
        title="진행 안내 부족",
        affected_paths=("/start",),
        evidence_digest=digest("evidence"),
        recommendation="단계별 진행 상태를 표시한다",
        requires_human_review=True,
        user_impact="사용자가 다음 행동을 찾기 어렵다",
        required_synthetic_tests=("합성 사용성 시험",),
    )
    return ImprovementProposal(
        schema_version="apf.experience-improvement-proposal/v1",
        maximum_outcome=MaximumOutcome.IMPROVEMENT_PROPOSAL,
        platform_id=platform_id,
        candidate_commit=HEAD,
        generated_at=NOW,
        finding=finding,
        location="/start",
        evidence_digest=digest("evidence"),
        user_impact=finding.user_impact,
        recommendation=finding.recommendation,
        required_synthetic_tests=finding.required_synthetic_tests,
        requires_human_review=True,
        proposal_digest=digest("proposal"),
    )


def write_platform(root: Path, platform_id: str, *, foundry_root: Path = FOUNDRY) -> None:
    import json
    import subprocess as subprocess_module

    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "src" / "example.py").write_text("value = 1\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("# guide\n", encoding="utf-8")
    (root / "docs" / "long.md").write_text("# long\n" + ("long text line " * 15) + "\n", encoding="utf-8")
    (root / "arkaon.workspace.json").write_text(
        json.dumps(
            {
                "schema_version": "arkaon.workspace/v1",
                "platform_id": platform_id,
                "foundry_root": str(foundry_root),
                "allowed_analysis_roots": ["src", "docs"],
                "forbidden_globs": [".env"],
                "production_change_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    subprocess_module.run(["git", "init"], cwd=root, capture_output=True, check=True)
    subprocess_module.run(["git", "add", "."], cwd=root, capture_output=True, check=True)
    subprocess_module.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "init"],
        cwd=root,
        capture_output=True,
        check=True,
    )


def test_seed_reflective_case_reaches_shadow_stage() -> None:
    learning = ArkaonReflectiveLearning()
    case_id = seed_reflective_case(learning, proposal())
    assert case_id == case_id_for_proposal(proposal())
    assert learning.events[-1].action == "SYNTHETIC_SHADOWED"


def test_bridge_writes_eternian_review_and_change_proposal(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox", "state"):
        (foundry / folder).mkdir(parents=True)
    (foundry / "config" / "arkaon-admin-change-control.json").write_text(
        (FOUNDRY / "config" / "arkaon-admin-change-control.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (foundry / "config" / "arkaon-reflective-learning-policy.json").write_text(
        (FOUNDRY / "config" / "arkaon-reflective-learning-policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    case_id, inbox_path, change_id = bridge_experience_proposal(
        foundry_root=foundry,
        proposal=proposal(),
        run_id="run-1",
        now=NOW,
        dry_run=False,
    )
    assert case_id.startswith("refl-DEMO-")
    assert InboxStage.ETHERNIAN_REVIEW.value in inbox_path
    packet = (foundry / inbox_path).read_text(encoding="utf-8")
    assert "reflection-bridge-inbox" in packet
    controller = AdminChangeController(foundry_root=foundry)
    stored = controller.get_proposal(change_id)
    assert stored.case_id == case_id


def test_promote_to_operator_decision_requires_existing_eternian_packet(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox", "state"):
        (foundry / folder).mkdir(parents=True)
    (foundry / "config" / "arkaon-admin-change-control.json").write_text(
        (FOUNDRY / "config" / "arkaon-admin-change-control.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (foundry / "config" / "arkaon-reflective-learning-policy.json").write_text(
        (FOUNDRY / "config" / "arkaon-reflective-learning-policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _, _, _ = bridge_experience_proposal(
        foundry_root=foundry,
        proposal=proposal(),
        run_id="run-1",
        now=NOW,
        dry_run=False,
    )
    packet_id = "run-1-refl-DEMO-f1-reflection"
    path = promote_to_operator_decision(
        foundry_root=foundry,
        packet_id=packet_id,
        eternian_review_digest=digest("review"),
        now=NOW,
        dry_run=False,
    )
    assert InboxStage.OPERATOR_DECISION.value in path
    with pytest.raises(OrchestratorError, match="operator-decision requires eternian review first"):
        from apf.reflection_bridge import write_reflection_inbox_packet

        write_reflection_inbox_packet(
            foundry_root=foundry,
            document={
                "schema_version": "apf.reflection-bridge-inbox/v1",
                "packet_id": "bad",
                "stage": InboxStage.OPERATOR_DECISION.value,
                "platform_id": "DEMO",
                "summary": "demo",
                "production_change_allowed": False,
                "automatic_learning": False,
            },
            dry_run=False,
        )


def test_complete_operator_decision_appends_immutable_lesson(tmp_path: Path) -> None:
    learning = ArkaonReflectiveLearning()
    seed_reflective_case(learning, proposal())
    case_id = case_id_for_proposal(proposal())
    store = ReflectiveLessonStore(tmp_path / "reflective-lessons")
    path = complete_operator_decision_to_lesson(
        learning=learning,
        store=store,
        case_id=case_id,
        eternian_review_digest=digest("review"),
        decision=Decision.ACCEPT,
        decision_digest=digest("operator"),
        lesson_id="lesson-1",
        principle="진행상태를 명시한다",
        reusable_pattern="상태·다음행동·권리를 함께 제시",
        failure_or_rejection_reason="",
        now=NOW,
    )
    assert path.is_file()
    assert learning.events[-1].action == "LESSON_RECORDED"


def test_orchestrator_run_creates_reflection_bridge_packets(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox", "reports", "logs", "state"):
        (foundry / folder).mkdir(parents=True)
    for name in (
        "shared-policy.json",
        "resource-limits.json",
        "platforms.json",
        "arkaon-experience-operations-audit.json",
        "arkaon-admin-change-control.json",
        "arkaon-reflective-learning-policy.json",
        "arkaon-public-surface-observation.json",
        "arkaon-predeployment-readiness.json",
        "arkaon-research-watch.json",
        "research-watch-sources.json",
        "arkaon-mobility-plaza-governance.json",
        "arkaon-map-ops-gate.json",
        "map-competency-profile.json",
        "map-provider-knowledge.provisional.json",
    ):
        (foundry / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    import json

    platforms = json.loads((foundry / "config" / "platforms.json").read_text(encoding="utf-8"))
    platforms["foundry_root"] = str(foundry)
    platforms["platforms"] = [{"id": "DEMO", "path": str(tmp_path / "demo-platform"), "enabled": True}]
    (foundry / "config" / "platforms.json").write_text(json.dumps(platforms), encoding="utf-8")
    (foundry / "knowledge" / "readiness").mkdir(parents=True, exist_ok=True)
    (foundry / "knowledge" / "readiness" / "v0.1-readiness.json").write_text(
        json.dumps({"schema_version": "apf.readiness-matrix/v1", "as_of_phase": "085"}),
        encoding="utf-8",
    )
    platform = tmp_path / "demo-platform"
    write_platform(platform, "DEMO", foundry_root=foundry)
    orchestrator = CentralOrchestrator.from_config(foundry)
    report = orchestrator.run((PlatformRegistration("DEMO", platform),))
    assert report.production_change_allowed is False
    assert any("reflection" in path for path in report.inbox_packets), (
        "reflection bridge should append eternian-review packets when findings exist"
    )
    assert any("experience" in path for path in report.inbox_packets)
