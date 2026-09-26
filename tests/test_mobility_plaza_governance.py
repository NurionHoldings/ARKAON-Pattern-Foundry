import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apf.mobility_plaza import (
    CoarsePlazaCell,
    MobilityPlaza,
    MobilityPlazaFoundation,
    PlazaPurpose,
    PlazaRejected,
)
from apf.mobility_plaza_bridge import bridge_plaza_governance_report
from apf.mobility_plaza_governance import GovernanceStatus, PlazaGovernanceHarness

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _foundation() -> MobilityPlazaFoundation:
    service = MobilityPlazaFoundation()
    service.register(
        MobilityPlaza(
            plaza_id="plaza-1",
            branch_id="branch-1",
            name="demo plaza",
            purposes=frozenset({PlazaPurpose.REST, PlazaPurpose.PEER_NOTICE}),
            cell=CoarsePlazaCell("wydm3", 5),
            created_at=NOW,
        )
    )
    service.join(
        plaza_id="plaza-1",
        rider_id="rider-a",
        consent=True,
        now=NOW,
        ttl=timedelta(hours=1),
    )
    return service


def test_plaza_governance_passes_clean_foundation(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    (foundry / "config").mkdir(parents=True)
    (foundry / "config" / "arkaon-mobility-plaza-governance.json").write_text(
        (FOUNDRY / "config" / "arkaon-mobility-plaza-governance.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    report = PlazaGovernanceHarness(foundry_root=foundry).audit_foundation(
        platform_id="DEMO",
        foundation=_foundation(),
        now=NOW,
    )
    assert report.overall is GovernanceStatus.PASS


def test_forbidden_plaza_use_stays_blocked():
    service = _foundation()
    with pytest.raises(PlazaRejected, match="labor control"):
        service.assert_use_allowed("dispatch_queue")


def test_platform_config_with_dispatch_writes_governance_packet(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    (foundry / "config").mkdir(parents=True)
    (foundry / "inbox" / "eternian-review").mkdir(parents=True)
    (foundry / "config" / "arkaon-mobility-plaza-governance.json").write_text(
        (FOUNDRY / "config" / "arkaon-mobility-plaza-governance.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    platform = tmp_path / "platform"
    (platform / "config").mkdir(parents=True)
    (platform / "config" / "mobility-plaza.json").write_text(
        json.dumps({"dispatch_from_plaza": True}),
        encoding="utf-8",
    )
    harness = PlazaGovernanceHarness(foundry_root=foundry)
    report = harness.audit_platform_config(platform_id="DEMO", platform_path=platform, now=NOW)
    assert report is not None
    assert report.overall is GovernanceStatus.FAIL
    path = bridge_plaza_governance_report(
        foundry_root=foundry,
        report=report,
        run_id="run-1",
        now=NOW,
        dry_run=False,
    )
    assert path and "plaza-gov" in path
