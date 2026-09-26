import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apf.map_ops_bridge import bridge_map_ops_gate_report
from apf.map_ops_gate import (
    DeviceAuthSession,
    EtaShadowObservation,
    GateStatus,
    MapOpsGateHarness,
    MapOpsGateRejected,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _mini_foundry(tmp_path: Path) -> Path:
    root = tmp_path / "foundry"
    (root / "config").mkdir(parents=True)
    (root / "inbox" / "eternian-review").mkdir(parents=True)
    for name in (
        "arkaon-map-ops-gate.json",
        "map-competency-profile.json",
        "map-provider-knowledge.provisional.json",
    ):
        (root / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return root


def test_map_ops_gate_passes_with_blocked_production_profile(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    report = MapOpsGateHarness(foundry_root=root).run(platform_id="ARKAON_FOUNDRY", now=NOW)
    assert report.overall in {GateStatus.PASS, GateStatus.ADVISORY}
    assert any(item.gate_id == "MAP_KNOWLEDGE_071" and item.status is GateStatus.PASS for item in report.results)
    assert any(item.gate_id == "MAP_RELEASE_076" and item.status is GateStatus.PASS for item in report.results)


def test_eta_shadow_advisory_emits_inbox_packet(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    report = MapOpsGateHarness(foundry_root=root).run(
        platform_id="ARKAON_FOUNDRY",
        now=NOW,
        eta_observation=EtaShadowObservation("route-1", 600, 3600),
    )
    assert report.overall is GateStatus.ADVISORY
    path = bridge_map_ops_gate_report(
        foundry_root=root,
        report=report,
        run_id="run-1",
        now=NOW,
        dry_run=False,
    )
    assert path and "map-ops" in path


def test_device_auth_rejects_continuous_tracking(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    session = DeviceAuthSession(
        device_id_hash="d" * 64,
        rider_id_hash="r" * 64,
        granted_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        continuous_tracking=True,
    )
    report = MapOpsGateHarness(foundry_root=root).run(
        platform_id="ARKAON_FOUNDRY",
        now=NOW,
        device_session=session,
    )
    assert report.overall is GateStatus.FAIL


def test_map_ops_policy_rejects_production_activation(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    document = json.loads((root / "config" / "arkaon-map-ops-gate.json").read_text(encoding="utf-8"))
    document["production_activation_allowed"] = True
    (root / "config" / "arkaon-map-ops-gate.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(MapOpsGateRejected, match="non-production"):
        MapOpsGateHarness(foundry_root=root)
