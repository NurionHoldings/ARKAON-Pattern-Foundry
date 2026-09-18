from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.reuse_proof_measurement import (
    MeasurementStatus,
    ReuseMeasurementRejected,
    ReuseProofMeasurementHarness,
)

ROOT = Path(__file__).parents[1]


def test_synthetic_measurement_meets_reduction_target():
    report = ReuseProofMeasurementHarness(foundry_root=ROOT).run(
        now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=True
    )
    assert report.overall is MeasurementStatus.PASS
    assert report.reduction_percent >= 50.0
    assert len(report.reuse_proof_digest) == 64


def test_measurement_writes_report(tmp_path):
    baseline_dir = tmp_path / "knowledge" / "reuse-proof"
    baseline_dir.mkdir(parents=True)
    source = ROOT / "knowledge" / "reuse-proof" / "m6-synthetic-baseline.json"
    (baseline_dir / "m6-synthetic-baseline.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "arkaon-reuse-proof-measurement.json").write_text(
        (ROOT / "config" / "arkaon-reuse-proof-measurement.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    harness = ReuseProofMeasurementHarness(foundry_root=tmp_path)
    harness.run(now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=False)
    assert list((tmp_path / "state" / "reuse-proof-measurement").glob("*.json"))


def test_measurement_fails_when_reduction_target_not_met(tmp_path):
    baseline_dir = tmp_path / "knowledge" / "reuse-proof"
    baseline_dir.mkdir(parents=True)
    document = {
        "schema_version": "apf.reuse-proof-baseline/v1",
        "baseline_metrics": {"planning_hours": 10.0},
        "reuse_metrics": {"planning_hours": 9.0},
        "approved_patterns": [
            {"pattern_id": "a", "status": "PUBLIC_PATTERN_APPROVED", "package_hash": "sha256:" + "1" * 64},
            {"pattern_id": "b", "status": "PUBLIC_PATTERN_APPROVED", "package_hash": "sha256:" + "2" * 64},
            {"pattern_id": "c", "status": "PUBLIC_PATTERN_APPROVED", "package_hash": "sha256:" + "3" * 64},
        ],
    }
    (baseline_dir / "m6-synthetic-baseline.json").write_text(
        __import__("json").dumps(document), encoding="utf-8"
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "arkaon-reuse-proof-measurement.json").write_text(
        '{"schema_version":"apf.arkaon-reuse-proof-measurement/v1","minimum_reduction_percent":50}',
        encoding="utf-8",
    )
    with pytest.raises(ReuseMeasurementRejected, match="synthetic reduction"):
        ReuseProofMeasurementHarness(foundry_root=tmp_path).run(
            now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=True
        )
