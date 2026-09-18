import json
from datetime import UTC, datetime
from pathlib import Path

from apf.analysis_target_resolution import (
    AnalysisTargetResolutionReport,
    CrossPlatformTarget,
    LastUserSiteRequest,
)
from apf.cross_platform_learning import (
    CrossPlatformLearningEngine,
    build_surface_observation_document,
    compare_and_abstract_patterns,
    flow_markers_from_html,
    infer_routes_from_landing_intent,
)
from apf.cross_platform_learning_bridge import bridge_cross_platform_learning_report

NOW = datetime(2031, 7, 1, tzinfo=UTC)


def _write_policy(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-cross-platform-learning.json").write_text(
        json.dumps({"schema_version": "apf.cross-platform-learning/v1", "execute_public_fetch": False}),
        encoding="utf-8",
    )


def _write_landing(tmp_path: Path, platform_id: str, patterns: list[str], signals: list[str], name: str) -> None:
    intents = tmp_path / "knowledge" / "landing-intents"
    intents.mkdir(parents=True, exist_ok=True)
    (intents / name).write_text(
        json.dumps(
            {
                "platform": {"id": platform_id},
                "learning_focus": {"priority_patterns": patterns},
                "landing_intent": {"signal": signals},
            }
        ),
        encoding="utf-8",
    )


def test_flow_markers_detect_e_contract_structure():
    html = "<h1>Step 1</h1><p>전자계약</p><section>비교</section><div>마이페이지</div>"
    markers = flow_markers_from_html(html)
    assert "flow/electronic-contract" in markers
    assert "flow/step-select" in markers
    assert "surface/comparison-matrix" in markers


def test_compare_and_abstract_patterns_from_shared_routes():
    proposals = compare_and_abstract_patterns(
        source_platform_id="ZAKSIMSPACE",
        target_platform_ids=("MAEJINNAM",),
        sought_tokens=frozenset({"landing-pattern:four-step-process", "landing-pattern:hero-single-cta"}),
        platform_routes={
            "ZAKSIMSPACE": frozenset({"flow/step-select", "surface/hero-primary-cta"}),
            "MAEJINNAM": frozenset({"flow/step-select", "surface/hero-primary-cta"}),
        },
        platform_digests={"ZAKSIMSPACE": "a" * 64, "MAEJINNAM": "b" * 64},
        minimum_platforms=2,
    )
    pattern_tokens = {item.pattern_token for item in proposals}
    assert "landing-pattern:four-step-process" in pattern_tokens
    assert "landing-pattern:hero-single-cta" in pattern_tokens


def test_engine_executes_learning_loop_without_network(tmp_path):
    _write_policy(tmp_path)
    _write_landing(
        tmp_path,
        "ZAKSIMSPACE",
        ["four-step-process", "hero-single-cta"],
        ["four_step_process_section", "single_primary_cta"],
        "zaksim.json",
    )
    _write_landing(
        tmp_path,
        "MAEJINNAM",
        ["four-step-process", "hero-single-cta"],
        ["four_step_process_section", "single_primary_cta"],
        "maejin.json",
    )
    store = tmp_path / "state" / "surface-observations"
    store.mkdir(parents=True)
    zaksim_obs = build_surface_observation_document(
        platform_id="ZAKSIMSPACE",
        source_url="https://zaksimspace.co.kr/",
        payload=b"<html>Step 1 Step 2 Step 3 Step 4 CTA</html>",
        now=NOW,
    )
    (store / "zaksim.json").write_text(json.dumps(zaksim_obs), encoding="utf-8")

    resolution = AnalysisTargetResolutionReport(
        foundry_root=tmp_path,
        evaluated_at=NOW,
        ambiguous=True,
        ambiguity_reason="LAST_REQUEST_NOT_IN_REGISTRY",
        last_user_site=LastUserSiteRequest(
            platform_id="ZAKSIMSPACE",
            sought_capability_tokens=(
                "landing-pattern:four-step-process",
                "landing-pattern:hero-single-cta",
            ),
            recorded_at=NOW,
            evidence_ref="inbox/operator-decision/test.json",
        ),
        targets=(
            CrossPlatformTarget(
                platform_id="MAEJINNAM",
                capability_tokens=("landing-pattern:four-step-process", "landing-pattern:hero-single-cta"),
                rationale="continue learning",
            ),
        ),
        report_digest="c" * 64,
    )

    engine = CrossPlatformLearningEngine(foundry_root=tmp_path)
    report = engine.execute(resolution_report=resolution, now=NOW, dry_run=False)
    assert report.pattern_proposals
    assert report.lesson_seeds
    pattern_path = tmp_path / "knowledge" / "landing-structure-patterns" / "proposed"
    assert any(pattern_path.glob("*.json"))
    paths = bridge_cross_platform_learning_report(
        foundry_root=tmp_path,
        report=report,
        policy=engine.policy,
        run_id="run-learn",
        now=NOW,
        dry_run=False,
    )
    assert paths
    packet = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert packet["packet_kind"] == "CROSS_PLATFORM_LESSON_SEED"
