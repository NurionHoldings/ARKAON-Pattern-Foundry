import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.sns_trend_analysis import SNSTrendAnalyzer, SNSTrendRejected, normalize_trend_item
from apf.sns_trend_bridge import bridge_sns_trend_report
from apf.sns_watch import structural_signals_from_manifest

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def test_normalize_trend_item_rejects_urls():
    with pytest.raises(SNSTrendRejected, match="abstract tags"):
        normalize_trend_item(
            {
                "item_id": "bad",
                "category_tag": "https://example.org",
                "content_angle_tag": "hook",
                "click_velocity_bin": "surge",
            }
        )


def test_structural_signals_include_trend_summary():
    manifest = json.loads((FOUNDRY / "knowledge/sns-digests/maejinnam.json").read_text(encoding="utf-8"))
    signals = structural_signals_from_manifest(manifest)
    assert signals["trend_surge_count"] == 1
    assert "limited-drop-countdown" in signals["trend_surge_item_ids"]


def test_sns_trend_analyzer_emits_market_proposals(tmp_path: Path):
    root = tmp_path / "foundry"
    (root / "config").mkdir(parents=True)
    (root / "inbox" / "research").mkdir(parents=True)
    (root / "config" / "arkaon-sns-trend.json").write_text(
        (FOUNDRY / "config" / "arkaon-sns-trend.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "config" / "sns-watch-sources.json").write_text(
        (FOUNDRY / "config" / "sns-watch-sources.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    rel = Path("knowledge/sns-digests/maejinnam.json")
    target = root / rel
    target.parent.mkdir(parents=True)
    target.write_text((FOUNDRY / rel).read_text(encoding="utf-8"), encoding="utf-8")

    report = SNSTrendAnalyzer(foundry_root=root).analyze(now=NOW)
    assert report.surge_items
    assert report.proposals
    paths = bridge_sns_trend_report(
        foundry_root=root,
        report=report,
        run_id="run-trend",
        now=NOW,
        dry_run=False,
    )
    assert any("sns-trend-analysis" in path for path in paths)
    assert any("sns-market-limited-drop-countdown" in path for path in paths)
