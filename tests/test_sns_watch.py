import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from apf.sns_watch import (
    SNSChangeKind,
    SNSWatchPolicy,
    SNSWatchRegistry,
    SNSWatchRejected,
    classify_signal_delta,
    structural_signals_from_html,
    structural_signals_from_manifest,
)
from apf.sns_watch_bridge import bridge_sns_watch_events

FOUNDRY = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)


def _mini_foundry(tmp_path: Path) -> Path:
    root = tmp_path / "foundry"
    (root / "config").mkdir(parents=True)
    (root / "inbox" / "research").mkdir(parents=True)
    for name in ("arkaon-sns-watch.json", "sns-watch-sources.json"):
        (root / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    sources = json.loads((root / "config" / "sns-watch-sources.json").read_text(encoding="utf-8"))
    for item in sources["sources"]:
        if item.get("kind") != "LOCAL_MANIFEST":
            item["enabled"] = False
            continue
        rel = Path(str(item["path"]))
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            source = FOUNDRY / rel
            target.write_text(
                source.read_text(encoding="utf-8") if source.is_file() else json.dumps({"observation_signals": {}}),
                encoding="utf-8",
            )
    (root / "config" / "sns-watch-sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return root


def test_structural_signals_from_html_without_verbatim_storage():
    html = b"""
    <html><head>
    <meta property="og:type" content="website"/>
    <meta property="og:title" content="ignored for storage"/>
    </head><body>
    <a href="https://example.org/one">x</a>
    <a href="https://example.org/two">y</a>
    <script src="https://cdn.example/app.js"></script>
    </body></html>
    """
    signals = structural_signals_from_html(html)
    assert signals["link_count_bin"] == "2-3"
    assert "og:type" in signals["og_property_samples"]
    assert "ignored for storage" not in json.dumps(signals)


def test_classify_feature_change_from_manifest_delta():
    previous = {
        "feature_tags": ["shop-link"],
        "format_tags": ["carousel"],
        "environment_tags": ["mobile-first-layout"],
    }
    current = {
        "feature_tags": ["shop-link", "live-badge"],
        "format_tags": ["carousel"],
        "environment_tags": ["mobile-first-layout"],
    }
    kind, delta = classify_signal_delta(previous=previous, current=current)
    assert kind is SNSChangeKind.FEATURE_CHANGE
    assert "feature_tags" in delta


def test_sns_watch_runs_on_scheduled_hour_and_writes_research_packet(tmp_path: Path):
    root = _mini_foundry(tmp_path)
    registry = SNSWatchRegistry(foundry_root=root)
    events = registry.analyze(now=NOW, force=True)
    assert events
    paths = bridge_sns_watch_events(
        foundry_root=root,
        events=events,
        run_id="run-sns",
        now=NOW,
        dry_run=False,
    )
    assert paths
    assert any("sns-maejinnam-sns-digest" in path for path in paths)


def test_sns_watch_skips_outside_scheduled_hour(tmp_path: Path):
    root = _mini_foundry(tmp_path)
    registry = SNSWatchRegistry(foundry_root=root)
    off_hour = datetime(2026, 9, 17, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)
    assert registry.analyze(now=off_hour) == ()


def test_sns_policy_rejects_verbatim_storage_flag(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "apf.sns-watch/v1",
                "verbatim_post_storage_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SNSWatchRejected, match="non-verbatim"):
        SNSWatchPolicy.load(bad)


def test_manifest_rejects_verbatim_post_storage():
    with pytest.raises(SNSWatchRejected, match="not allowed"):
        structural_signals_from_manifest({"verbatim_post_storage": True, "observation_signals": {}})
