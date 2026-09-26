import json
from datetime import UTC, datetime
from pathlib import Path

from apf.asset_investigation import AssetInvestigationHarness, InvestigationKind
from apf.asset_investigation_bridge import bridge_asset_investigation_report
from apf.research_watch import WatchEvent

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _mini_foundry(tmp_path: Path) -> Path:
    root = tmp_path / "foundry"
    for rel in (
        "config",
        "knowledge/patterns/candidates",
        "knowledge/pilots",
        "state/surface-observations",
        "inbox/research",
    ):
        (root / rel).mkdir(parents=True)
    for name in ("arkaon-asset-investigation.json", "pattern-promotion-manifest.json"):
        (root / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    for path in sorted((FOUNDRY / "knowledge/patterns/candidates").glob("*.json")):
        (root / "knowledge/patterns/candidates" / path.name).write_text(
            path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    for path in sorted((FOUNDRY / "knowledge/pilots").glob("*-041.json")):
        (root / "knowledge/pilots" / path.name).write_text(
            path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return root


def test_asset_investigation_ranks_research_delta_and_owned_pilot_gaps(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    events = (
        WatchEvent(
            watch_id="shared-policy",
            platform_id="ARKAON_FOUNDRY",
            previous_digest="a" * 64,
            current_digest="b" * 64,
            changed=True,
            observed_at=NOW,
        ),
    )
    report = AssetInvestigationHarness(foundry_root=root).run(now=NOW, watch_events=events)
    assert report.priorities
    assert report.priorities[0].kind is InvestigationKind.RESEARCH_DELTA
    kinds = {item.kind for item in report.priorities}
    assert InvestigationKind.OWNED_PILOT_GAP in kinds
    assert InvestigationKind.PATTERN_CANDIDATE in kinds


def test_asset_investigation_emits_research_packet_when_score_high(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    events = (
        WatchEvent(
            watch_id="foundry-readiness",
            platform_id="ARKAON_FOUNDRY",
            previous_digest=None,
            current_digest="c" * 64,
            changed=True,
            observed_at=NOW,
        ),
    )
    harness = AssetInvestigationHarness(foundry_root=root)
    report = harness.run(now=NOW, watch_events=events)
    path = bridge_asset_investigation_report(
        foundry_root=root,
        report=report,
        policy=harness.policy,
        run_id="run-1",
        now=NOW,
        dry_run=False,
    )
    assert path and "asset-investigation" in path
    document = json.loads(
        (root / "inbox" / "research" / "run-1-asset-investigation.json").read_text(encoding="utf-8")
    )
    assert document["top_priorities"]
