import json
from datetime import UTC, datetime
from pathlib import Path

from apf.intent_dna_self_repair import (
    FeatureContributor,
    IntentDnaSelfRepairEngine,
    IntentDnaSelfRepairPolicy,
    build_pass0_seed_document,
)
from apf.intent_dna_self_repair_bridge import bridge_intent_dna_self_repair_report

NOW = datetime(2026, 9, 19, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _write_min_feature(foundry: Path, feature_id: str) -> None:
    (foundry / "config").mkdir(parents=True, exist_ok=True)
    (foundry / "src" / "apf").mkdir(parents=True, exist_ok=True)
    config_path = foundry / "config" / f"arkaon-{feature_id}.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": f"apf.{feature_id}/v1",
                "enabled": True,
                "notes": ["added by beom without intent seed"],
            }
        ),
        encoding="utf-8",
    )
    module_path = foundry / "src" / "apf" / f"{feature_id.replace('-', '_')}.py"
    module_path.write_text(
        f'"""Beom-added feature module for {feature_id}."""\n',
        encoding="utf-8",
    )


def test_detects_missing_feature_intent_and_generates_pass0_seed(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    _write_min_feature(foundry, "demo-feature")
    (foundry / "config" / "arkaon-intent-dna-self-repair.json").write_text(
        (FOUNDRY / "config" / "arkaon-intent-dna-self-repair.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    engine = IntentDnaSelfRepairEngine(foundry_root=foundry)
    report = engine.analyze(now=NOW, dry_run=False)

    assert len(report.missing_features) == 1
    assert report.missing_features[0].feature_id == "demo-feature"
    assert report.missing_features[0].reason == "FEATURE_INTENT_SEED_MISSING"
    assert report.missing_features[0].contributor is FeatureContributor.BEOM
    assert len(report.generated_seeds) == 1
    seed_path = foundry / "knowledge" / "feature-intents" / "demo-feature.json"
    assert seed_path.is_file()
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    assert seed["phase"] == "PASS0_SELF_GENERATED"
    assert seed["authorization"]["basis"] == "SELF_DIAGNOSIS_SELF_GENERATION"
    assert seed["gates"]["locked"] is False
    assert seed["gates"]["intent_dna_mutation"] is False


def test_self_generation_forbidden_when_policy_disabled(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    _write_min_feature(foundry, "demo-feature")
    policy = IntentDnaSelfRepairPolicy(self_generation_allowed=False)
    engine = IntentDnaSelfRepairEngine(foundry_root=foundry, policy=policy)
    report = engine.analyze(now=NOW, dry_run=False)

    assert len(report.missing_features) == 1
    assert report.generated_seeds == ()
    assert not (foundry / "knowledge" / "feature-intents" / "demo-feature.json").exists()


def test_bridge_emits_research_and_eternian_packets(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    _write_min_feature(foundry, "demo-feature")
    engine = IntentDnaSelfRepairEngine(foundry_root=foundry)
    report = engine.analyze(now=NOW, dry_run=True)
    paths = bridge_intent_dna_self_repair_report(
        foundry_root=foundry,
        report=report,
        policy=engine.policy,
        run_id="run-demo",
        now=NOW,
        dry_run=False,
    )

    assert len(paths) == 2
    assert (foundry / "inbox" / "research" / "run-demo-intent-dna-self-repair-research.json").is_file()
    assert (foundry / "inbox" / "eternian-review" / "run-demo-intent-dna-self-repair-eternian.json").is_file()


def test_build_pass0_seed_document_is_deterministic(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    _write_min_feature(foundry, "demo-feature")
    config_path = foundry / "config" / "arkaon-demo-feature.json"
    first = build_pass0_seed_document(
        feature_id="demo-feature",
        contributor=FeatureContributor.BEOM,
        foundry_root=foundry,
        config_path=config_path,
    )
    second = build_pass0_seed_document(
        feature_id="demo-feature",
        contributor=FeatureContributor.BEOM,
        foundry_root=foundry,
        config_path=config_path,
    )
    assert first["fingerprint"] == second["fingerprint"]
    assert first["completeness"] >= 0.8
