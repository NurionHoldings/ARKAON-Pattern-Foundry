import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.learning_impediment import (
    EngineLimitSnapshot,
    LearningImpedimentEngine,
    LearningImpedimentRejected,
)
from apf.learning_impediment_bridge import bridge_learning_impediment_report

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _write_config(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    for name in (
        "arkaon-learning-impediment.json",
        "arkaon-accumulation-policy.json",
        "collector.default.json",
        "arkaon-hourly-learning-schedule.json",
        "arkaon-evolution-domains.json",
        "arkaon-reflective-learning-policy.json",
    ):
        source = FOUNDRY / "config" / name
        if source.is_file():
            (root / "config" / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_engine_detects_bounded_resource_limits(tmp_path: Path):
    root = tmp_path / "foundry"
    _write_config(root)
    (root / "config" / "resource-limits.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.resource-limits/v1",
                "max_platforms_per_run": 2,
                "max_inbox_packets": 8,
                "max_files_per_platform": 100,
                "max_seconds_per_platform": 30,
                "max_memory_mb_per_platform": 256,
            }
        ),
        encoding="utf-8",
    )
    limits = EngineLimitSnapshot.from_foundry(root)
    report = LearningImpedimentEngine(foundry_root=root).analyze(now=NOW, limits=limits)
    kinds = {item.limit_kind for item in report.impediments}
    assert "BOUNDED_RESOURCE_LIMITS" in kinds
    targets = {
        request.target.value
        for impediment in report.impediments
        for request in impediment.modification_requests
    }
    assert "BEOM" in targets
    assert "ETERNIAN" in targets


def test_engine_detects_collection_response_too_large(tmp_path: Path):
    root = tmp_path / "foundry"
    _write_config(root)
    (root / "config" / "resource-limits.json").write_text(
        (FOUNDRY / "config" / "resource-limits.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    audit = root / "state" / "arkaon-collection-audit.jsonl"
    audit.parent.mkdir(parents=True)
    event = {
        "event": {
            "collected": False,
            "content_bytes": 9000000,
            "decision": "RESPONSE_TOO_LARGE",
            "locator": "https://example.org/large-doc",
            "occurred_at": NOW.isoformat(),
            "reusable": False,
            "source_id": "large-doc-source",
        }
    }
    audit.write_text(json.dumps(event) + "\n", encoding="utf-8")
    report = LearningImpedimentEngine(foundry_root=root).analyze(now=NOW)
    assert any(item.limit_kind == "COLLECTION_RESPONSE_TOO_LARGE" for item in report.impediments)


def test_bridge_writes_eternian_and_beom_packets(tmp_path: Path):
    root = tmp_path / "foundry"
    (root / "inbox" / "research").mkdir(parents=True)
    (root / "inbox" / "eternian-review").mkdir(parents=True)
    (root / "inbox" / "operator-decision").mkdir(parents=True)
    _write_config(root)
    (root / "config" / "resource-limits.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.resource-limits/v1",
                "max_platforms_per_run": 1,
                "max_inbox_packets": 4,
                "max_files_per_platform": 50,
                "max_seconds_per_platform": 10,
                "max_memory_mb_per_platform": 128,
            }
        ),
        encoding="utf-8",
    )
    engine = LearningImpedimentEngine(foundry_root=root)
    report = engine.analyze(now=NOW)
    paths = bridge_learning_impediment_report(
        foundry_root=root,
        report=report,
        policy=engine.policy,
        run_id="run-impediment",
        now=NOW,
        dry_run=False,
    )
    assert len(paths) >= 2
    stages = {Path(path).parent.name for path in paths}
    assert "research" in stages
    assert "eternian-review" in stages
    assert "operator-decision" in stages
    beom_doc = json.loads(
        (root / "inbox" / "operator-decision" / "run-impediment-learning-impediment-beom.json").read_text(
            encoding="utf-8"
        )
    )
    assert beom_doc["packet_kind"] == "LEARNING_MODIFICATION_REQUEST"
    assert beom_doc["modification_requests"]


def test_engine_detects_improvement_program_area_gap(tmp_path: Path):
    root = tmp_path / "foundry"
    _write_config(root)
    (root / "config" / "resource-limits.json").write_text(
        (FOUNDRY / "config" / "resource-limits.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "config" / "arkaon-experience-operations-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.arkaon-experience-operations-audit.v1",
                "areas": ["OFFICIAL_BENCHMARK"],
                "maximum_outcome": "IMPROVEMENT_PROPOSAL",
                "automatic_change_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    report = LearningImpedimentEngine(foundry_root=root).analyze(now=NOW)
    assert any(item.limit_kind == "IMPROVEMENT_PROGRAM_AREA_GAP" for item in report.impediments)


def test_engine_detects_reflective_storage_disabled(tmp_path: Path):
    root = tmp_path / "foundry"
    _write_config(root)
    (root / "config" / "resource-limits.json").write_text(
        (FOUNDRY / "config" / "resource-limits.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    reflective = json.loads((FOUNDRY / "config" / "arkaon-reflective-learning-policy.json").read_text(encoding="utf-8"))
    reflective["records_rejected_and_failed_lessons"] = False
    (root / "config" / "arkaon-reflective-learning-policy.json").write_text(
        json.dumps(reflective), encoding="utf-8"
    )
    for relative in ("state", "knowledge", "inbox", "state/hourly-learning", "knowledge/shorts-production-assets"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    report = LearningImpedimentEngine(foundry_root=root).analyze(now=NOW)
    assert any(item.limit_kind == "STORAGE_REFLECTIVE_RECORDING_DISABLED" for item in report.impediments)


def test_policy_rejects_auto_implement(tmp_path: Path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-learning-impediment.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.learning-impediment/v1",
                "automatic_implement_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LearningImpedimentRejected, match="request-only"):
        LearningImpedimentEngine(foundry_root=tmp_path)
