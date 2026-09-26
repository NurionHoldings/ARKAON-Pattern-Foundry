import json
from datetime import UTC, datetime
from pathlib import Path

from apf.analysis_target_resolution import (
    AnalysisTargetResolutionEngine,
    LastUserSiteRequest,
    detect_ambiguity,
    load_sought_capability_tokens,
    plan_cross_platform_targets,
    refresh_last_user_site_request,
)
from apf.analysis_target_resolution_bridge import bridge_analysis_target_resolution_report

NOW = datetime(2031, 6, 1, tzinfo=UTC)


def _write_landing_intent(tmp_path: Path, platform_id: str, patterns: list[str], name: str) -> None:
    intents = tmp_path / "knowledge" / "landing-intents"
    intents.mkdir(parents=True, exist_ok=True)
    (intents / name).write_text(
        json.dumps(
            {
                "platform": {"id": platform_id},
                "learning_focus": {"priority_patterns": patterns},
                "landing_intent": {"signal": ["single_primary_cta"]},
                "evolution_domain_refs": ["HOME_SURFACE_OPTIMIZATION"],
            }
        ),
        encoding="utf-8",
    )


def _write_policy(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-analysis-target-resolution.json").write_text(
        json.dumps({"schema_version": "apf.analysis-target-resolution/v1"}),
        encoding="utf-8",
    )


def test_load_sought_capability_tokens_from_landing_intent(tmp_path):
    _write_landing_intent(tmp_path, "MAEJINNAM", ["hero-single-cta"], "maejinnam.json")
    tokens = load_sought_capability_tokens(tmp_path, "MAEJINNAM")
    assert "landing-pattern:hero-single-cta" in tokens
    assert "landing-signal:single_primary_cta" in tokens
    assert "evolution-domain:HOME_SURFACE_OPTIMIZATION" in tokens


def test_detect_ambiguity_when_last_request_not_in_registry():
    ambiguous, reason = detect_ambiguity(
        enabled_registration_count=1,
        enabled_paths_missing=False,
        last_request_not_in_registry=True,
        all_platforms_blocked=False,
    )
    assert ambiguous
    assert reason == "LAST_REQUEST_NOT_IN_REGISTRY"


def test_plan_cross_platform_targets_skips_duplicate_ledger_entries(tmp_path):
    _write_policy(tmp_path)
    _write_landing_intent(tmp_path, "MAEJINNAM", ["hero-single-cta"], "maejinnam.json")
    _write_landing_intent(tmp_path, "DOSIRAK_STORE", ["proof-before-offer"], "dosirak.json")
    _write_landing_intent(tmp_path, "WITHER", ["waitlist-single-cta"], "wither.json")
    store = tmp_path / "state" / "analysis-target-resolution"
    store.mkdir(parents=True)
    (store / "analysis-ledger.jsonl").write_text(
        json.dumps({"platform_id": "DOSIRAK_STORE", "capability_token": "landing-pattern:hero-single-cta"}) + "\n",
        encoding="utf-8",
    )
    last_request = LastUserSiteRequest(
        platform_id="MAEJINNAM",
        sought_capability_tokens=("landing-pattern:hero-single-cta",),
        recorded_at=NOW,
        evidence_ref="inbox/operator-decision/sample.json",
    )
    targets = plan_cross_platform_targets(
        foundry_root=tmp_path,
        last_request=last_request,
        registered_platform_ids=frozenset({"NARANG_RIDER"}),
        ledger={("DOSIRAK_STORE", "landing-pattern:hero-single-cta")},
        max_targets=3,
    )
    platform_ids = {item.platform_id for item in targets}
    assert "DOSIRAK_STORE" not in platform_ids
    assert "WITHER" in platform_ids


def test_engine_emits_cross_platform_targets_when_ambiguous(tmp_path):
    _write_policy(tmp_path)
    _write_landing_intent(tmp_path, "MAEJINNAM", ["hero-single-cta"], "maejinnam.json")
    _write_landing_intent(tmp_path, "DOSIRAK_STORE", ["proof-before-offer"], "dosirak.json")
    inbox = tmp_path / "inbox" / "operator-decision"
    inbox.mkdir(parents=True)
    (inbox / "maejinnam-focus.json").write_text(
        json.dumps(
            {
                "platform_id": "MAEJINNAM",
                "created_at": NOW.isoformat(),
                "summary": "analyze maejinnam landing scarcity framing",
            }
        ),
        encoding="utf-8",
    )
    engine = AnalysisTargetResolutionEngine(foundry_root=tmp_path)
    report = engine.analyze(
        now=NOW,
        run_id="run-cross",
        dry_run=False,
        enabled_registration_count=1,
        enabled_paths_missing=False,
        registered_platform_ids=frozenset({"NARANG_RIDER"}),
        all_platforms_blocked=False,
    )
    assert report.ambiguous
    assert report.ambiguity_reason == "LAST_REQUEST_NOT_IN_REGISTRY"
    assert report.last_user_site is not None
    assert report.last_user_site.platform_id == "MAEJINNAM"
    assert report.targets
    paths = bridge_analysis_target_resolution_report(
        foundry_root=tmp_path,
        report=report,
        policy=engine.policy,
        run_id="run-cross",
        now=NOW,
        dry_run=False,
    )
    assert len(paths) == 1
    packet = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert packet["packet_kind"] == "CROSS_PLATFORM_ANALYSIS_CONTINUATION"
    assert packet["targets"]


def test_refresh_last_user_site_request_from_operator_inbox(tmp_path):
    _write_policy(tmp_path)
    _write_landing_intent(tmp_path, "MAEJINNAM", ["hero-single-cta"], "maejinnam.json")
    inbox = tmp_path / "inbox" / "operator-decision"
    inbox.mkdir(parents=True)
    (inbox / "focus.json").write_text(
        json.dumps({"platform_id": "MAEJINNAM", "created_at": NOW.isoformat()}),
        encoding="utf-8",
    )
    store = tmp_path / "state" / "analysis-target-resolution"
    request = refresh_last_user_site_request(
        foundry_root=tmp_path,
        store_root=store,
        scan_operator_inbox=True,
        now=NOW,
        dry_run=False,
    )
    assert request is not None
    assert request.platform_id == "MAEJINNAM"
    assert (store / "last-user-site-request.json").is_file()
