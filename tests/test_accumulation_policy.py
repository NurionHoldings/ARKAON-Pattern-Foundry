import json
from datetime import UTC, datetime
from pathlib import Path

from apf.accumulation_policy import AccumulationPolicy, has_capacity, remaining_capacity
from apf.central_orchestrator import CentralOrchestrator, ResourceLimits
from apf.learning_curriculum import LearningCandidate, LearningOrigin, plan_curriculum
from apf.learning_memory import LearningLesson, LearningMemory, LessonOutcome

FOUNDRY = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def test_resource_limits_v2_unbounded_defaults():
    limits = ResourceLimits.load(FOUNDRY / "config" / "resource-limits.json")
    assert limits.is_unbounded
    assert limits.max_inbox_packets is None
    assert limits.max_platforms_per_run is None
    assert limits.sequential_platform_analysis is False


def test_accumulation_policy_loads_unbounded_memory():
    policy = AccumulationPolicy.load(FOUNDRY / "config" / "arkaon-accumulation-policy.json")
    assert policy.is_unbounded
    assert policy.failure_family_limit is None
    memory = LearningMemory.from_foundry(FOUNDRY)
    for index in range(5):
        memory.remember(
            LearningLesson(
                intent_fingerprint="intent",
                domain="collection",
                problem="lease",
                failure_mode="race",
                principle=f"principle-{index}",
                evidence_refs=(f"audit:{index}",),
                confidence=0.9,
                outcome=LessonOutcome.FAILURE,
                verified=True,
            )
        )
    assert len(memory) == 5


def test_has_capacity_helpers():
    assert has_capacity(10, None)
    assert has_capacity(10, 32)
    assert not has_capacity(32, 32)
    assert remaining_capacity(10, None) is None
    assert remaining_capacity(10, 32) == 22


def test_plan_curriculum_unbounded_selects_all_candidates():
    candidates = [
        LearningCandidate(
            candidate_id=f"c-{index}",
            origin=LearningOrigin.EXTERNAL if index % 2 == 0 else LearningOrigin.INTERNAL,
            knowledge_gap=0.8,
            failure_frequency=0.7,
            intent_relevance=0.8,
            novelty=0.5,
            estimated_cost=1,
        )
        for index in range(6)
    ]
    plan = plan_curriculum(candidates, max_items=None, budget_limit=None)
    assert len(plan.items) == 6


def test_orchestrator_unbounded_inbox(tmp_path: Path):
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox", "reports", "logs", "state"):
        (foundry / folder).mkdir(parents=True, exist_ok=True)
    for name in (
        "shared-policy.json",
        "resource-limits.json",
        "arkaon-accumulation-policy.json",
        "platforms.json",
    ):
        source = FOUNDRY / "config" / name
        if source.is_file():
            (foundry / "config" / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    platform_a = tmp_path / "platform-a"
    platform_b = tmp_path / "platform-b"
    for platform_id, platform_path in (("ALPHA", platform_a), ("BETA", platform_b)):
        platform_path.mkdir(parents=True)
        (platform_path / "src").mkdir()
        (platform_path / "docs").mkdir()
        (platform_path / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
        (platform_path / "docs" / "readme.md").write_text("# readme\n", encoding="utf-8")
        (platform_path / "arkaon.workspace.json").write_text(
            json.dumps(
                {
                    "schema_version": "arkaon.workspace/v1",
                    "platform_id": platform_id,
                    "foundry_root": str(foundry),
                    "allowed_analysis_roots": ["src", "docs"],
                    "forbidden_globs": [".env"],
                    "production_change_allowed": False,
                }
            ),
            encoding="utf-8",
        )

    orchestrator = CentralOrchestrator.from_config(foundry)
    from apf.central_orchestrator import PlatformRegistration

    report = orchestrator.run(
        (
            PlatformRegistration("ALPHA", platform_a),
            PlatformRegistration("BETA", platform_b),
        ),
        dry_run=True,
    )
    assert len(report.platform_reports) == 2
    assert len(report.inbox_packets) >= 4
