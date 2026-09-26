import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from apf.emerging_market_watch import (
    EmergingMarketWatchRegistry,
    EmergingMarketWatchRejected,
    MarketChangeKind,
    classify_market_delta,
    market_signals_from_manifest,
)
from apf.emerging_market_watch_bridge import bridge_emerging_market_events

FOUNDRY = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 17, 9, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)


def _mini_foundry(tmp_path: Path) -> Path:
    root = tmp_path / "foundry"
    (root / "config").mkdir(parents=True)
    (root / "inbox" / "research").mkdir(parents=True)
    for name in ("arkaon-emerging-market-watch.json", "emerging-market-sources.json"):
        (root / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    sources = json.loads((root / "config" / "emerging-market-sources.json").read_text(encoding="utf-8"))
    for item in sources["sources"]:
        if item.get("kind") != "LOCAL_MANIFEST":
            item["enabled"] = False
            continue
        rel = Path(str(item["path"]))
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        source = FOUNDRY / rel
        target.write_text(source.read_text(encoding="utf-8") if source.is_file() else "{}", encoding="utf-8")
    (root / "config" / "emerging-market-sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return root


def test_market_manifest_classifies_new_segment():
    previous = {
        "segment_tags": ["live-commerce"],
        "demand_tags": ["mobile-checkout"],
        "regulatory_tags": [],
        "novelty_score_bin": "stable",
    }
    current = {
        "segment_tags": ["live-commerce", "ai-copy-assist"],
        "demand_tags": ["mobile-checkout"],
        "regulatory_tags": [],
        "novelty_score_bin": "rising",
    }
    kind, delta = classify_market_delta(previous=previous, current=current)
    assert kind is MarketChangeKind.NEW_MARKET_SEGMENT
    assert "segment_tags" in delta


def test_emerging_market_watch_writes_research_packet(tmp_path: Path):
    root = _mini_foundry(tmp_path)
    registry = EmergingMarketWatchRegistry(foundry_root=root)
    events = registry.analyze(now=NOW, force=True)
    assert events
    paths = bridge_emerging_market_events(
        foundry_root=root,
        events=events,
        run_id="run-market",
        now=NOW,
        dry_run=False,
    )
    assert any("market-wave1-creator-commerce" in path for path in paths)


def test_emerging_market_skips_outside_schedule(tmp_path: Path):
    root = _mini_foundry(tmp_path)
    registry = EmergingMarketWatchRegistry(foundry_root=root)
    off_hour = datetime(2026, 9, 17, 8, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(UTC)
    assert registry.analyze(now=off_hour) == ()


def test_market_manifest_rejects_verbatim_storage():
    with pytest.raises(EmergingMarketWatchRejected, match="not allowed"):
        market_signals_from_manifest({"verbatim_storage": True, "observation_signals": {}})
