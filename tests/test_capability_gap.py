import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.capability_gap import CapabilityGapEngine, CapabilityGapRejected
from apf.capability_gap_bridge import bridge_capability_gap_report

NOW = datetime(2031, 1, 1, tzinfo=UTC)


def _surface(tmp_path: Path, platform_id: str, openapi_paths: list[str], name: str) -> None:
    store = tmp_path / "state" / "surface-observations"
    store.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": "apf.public-surface-observation/v1",
        "platform_id": platform_id,
        "openapi_paths": openapi_paths,
        "policy_route_refs": [],
        "js_structures": [],
        "observation_digest": "a" * 64,
    }
    (store / name).write_text(json.dumps(document), encoding="utf-8")


def test_engine_detects_external_capability_missing_on_owned_platform(tmp_path):
    _surface(tmp_path, "EXTERNAL_A", ["/v1/waitlist"], "external-a.json")
    _surface(tmp_path, "NARANG_RIDER", ["/"], "owned.json")
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-capability-gap.json").write_text(
        '{"schema_version":"apf.arkaon-capability-gap/v1"}', encoding="utf-8"
    )
    report = CapabilityGapEngine(foundry_root=tmp_path).analyze_owned_platform(
        owned_platform_id="NARANG_RIDER",
        owned_platform_path=None,
        now=NOW,
    )
    assert report.gaps
    gap = report.gaps[0]
    assert gap.capability_token == "api-surface:waitlist"
    assert "NARANG_RIDER" in gap.user_message
    assert "EXTERNAL_A" in gap.external_platform_ids
    assert len(gap.requested_actions) == 3


def test_bridge_writes_action_request_packets(tmp_path):
    _surface(tmp_path, "EXTERNAL_A", ["/v1/checkout"], "external-a.json")
    _surface(tmp_path, "OWNED", ["/"], "owned.json")
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-capability-gap.json").write_text(
        '{"schema_version":"apf.arkaon-capability-gap/v1"}', encoding="utf-8"
    )
    engine = CapabilityGapEngine(foundry_root=tmp_path)
    report = engine.analyze_owned_platform(owned_platform_id="OWNED", owned_platform_path=None, now=NOW)
    paths = bridge_capability_gap_report(
        foundry_root=tmp_path,
        report=report,
        policy=engine.policy,
        run_id="run123",
        now=NOW,
        dry_run=False,
    )
    assert len(paths) >= 2
    stages = {Path(path).parent.name for path in paths}
    assert "research" in stages
    assert "eternian-review" in stages


def test_landing_intent_patterns_included_in_inventory(tmp_path):
    intents = tmp_path / "knowledge" / "landing-intents"
    intents.mkdir(parents=True)
    (intents / "wither.json").write_text(
        json.dumps(
            {
                "platform": {"id": "WITHER"},
                "learning_focus": {"priority_patterns": ["waitlist-single-cta"]},
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-capability-gap.json").write_text(
        '{"schema_version":"apf.arkaon-capability-gap/v1"}', encoding="utf-8"
    )
    report = CapabilityGapEngine(foundry_root=tmp_path).analyze_owned_platform(
        owned_platform_id="NARANG_RIDER",
        owned_platform_path=None,
        now=NOW,
    )
    tokens = {gap.capability_token for gap in report.gaps}
    assert "landing-pattern:waitlist-single-cta" in tokens


def test_policy_rejects_auto_implement(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-capability-gap.json").write_text(
        '{"schema_version":"apf.arkaon-capability-gap/v1","automatic_implement_allowed":true}',
        encoding="utf-8",
    )
    with pytest.raises(CapabilityGapRejected, match="request-only"):
        CapabilityGapEngine(foundry_root=tmp_path)
