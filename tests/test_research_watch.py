import json
from datetime import UTC, datetime
from pathlib import Path

from apf.research_watch import ResearchWatchRegistry
from apf.research_watch_bridge import bridge_research_watch_events

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _mini_foundry(tmp_path: Path) -> Path:
    root = tmp_path / "foundry"
    (root / "config").mkdir(parents=True)
    (root / "inbox" / "research").mkdir(parents=True)
    for name in ("arkaon-research-watch.json", "research-watch-sources.json"):
        (root / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    readiness = {"schema_version": "apf.readiness-matrix/v1", "as_of_phase": "085"}
    (root / "knowledge" / "readiness").mkdir(parents=True)
    (root / "knowledge" / "readiness" / "v0.1-readiness.json").write_text(
        json.dumps(readiness),
        encoding="utf-8",
    )
    sources = json.loads((root / "config" / "research-watch-sources.json").read_text(encoding="utf-8"))
    for item in sources["sources"]:
        rel = Path(str(item["path"]))
        rel.parent.mkdir(parents=True, exist_ok=True)
        if not (root / rel).exists():
            (root / rel).write_text(json.dumps({"seed": item["watch_id"]}), encoding="utf-8")
    return root


def test_research_watch_detects_digest_change_and_writes_research_packet(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    registry = ResearchWatchRegistry(foundry_root=root)
    first = registry.detect_changes(now=NOW)
    assert first
    paths = bridge_research_watch_events(
        foundry_root=root,
        events=first,
        run_id="run-1",
        now=NOW,
        dry_run=False,
    )
    assert paths
    readiness_path = root / "knowledge" / "readiness" / "v0.1-readiness.json"
    document = json.loads(readiness_path.read_text(encoding="utf-8"))
    document["changed"] = True
    readiness_path.write_text(json.dumps(document), encoding="utf-8")
    second = registry.detect_changes(now=NOW)
    changed = [item for item in second if item.changed and item.previous_digest]
    assert changed
    paths = bridge_research_watch_events(
        foundry_root=root,
        events=tuple(changed),
        run_id="run-2",
        now=NOW,
        dry_run=False,
    )
    assert any("watch-foundry-readiness" in path for path in paths)
