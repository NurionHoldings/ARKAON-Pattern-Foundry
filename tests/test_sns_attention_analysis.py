from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.sns_attention_analysis import (
    SNSAttentionAnalyzer,
    SNSAttentionRejected,
    infer_attention_factors,
    normalize_attention_factors,
)
from apf.sns_attention_bridge import bridge_sns_attention_report
from apf.sns_trend_analysis import SNSTrendAnalyzer

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def test_normalize_attention_factors_rejects_urls():
    with pytest.raises(SNSAttentionRejected, match="abstract tag"):
        normalize_attention_factors({"primary_driver": "https://example.org"})


def test_infer_attention_factors_for_beat_sync():
    factors = infer_attention_factors(content_angle_tag="beat-sync-hook")
    assert factors["primary_driver"] == "motion-contrast-open"
    assert factors["audio_cue_tag"] == "beat-drop"


def test_sns_attention_analyzer_writes_assets_and_inbox(tmp_path: Path):
    root = tmp_path / "foundry"
    (root / "config").mkdir(parents=True)
    (root / "inbox" / "research").mkdir(parents=True)
    for name in ("arkaon-sns-trend.json", "arkaon-sns-attention.json", "sns-watch-sources.json"):
        (root / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    rel = Path("knowledge/sns-digests/maejinnam.json")
    target = root / rel
    target.parent.mkdir(parents=True)
    target.write_text((FOUNDRY / rel).read_text(encoding="utf-8"), encoding="utf-8")

    trend_report = SNSTrendAnalyzer(foundry_root=root).analyze(now=NOW)
    attention_report = SNSAttentionAnalyzer(foundry_root=root).analyze_surge_items(
        surge_items=trend_report.surge_items,
        now=NOW,
    )
    assert attention_report.assets
    asset = attention_report.assets[0]
    assert asset.factor_source == "manifest"
    assert asset.attention_factors["primary_driver"] == "scarcity-framing"
    assert (root / "knowledge/shorts-production-assets/maejinnam-limited-drop-countdown.json").is_file()

    paths = bridge_sns_attention_report(
        foundry_root=root,
        report=attention_report,
        run_id="run-attention",
        now=NOW,
        dry_run=False,
    )
    assert any("sns-attention-analysis" in path for path in paths)
    assert any("sns-attention-limited-drop-countdown" in path for path in paths)


def test_attention_bridge_skips_empty_report(tmp_path: Path):
    root = tmp_path / "foundry"
    analyzer = SNSAttentionAnalyzer(foundry_root=root)
    empty = analyzer.analyze_surge_items(surge_items=(), now=NOW)
    assert bridge_sns_attention_report(
        foundry_root=root,
        report=empty,
        run_id="run-empty",
        now=NOW,
        dry_run=False,
    ) == ()
