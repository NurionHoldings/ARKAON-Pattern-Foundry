import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.central_orchestrator import (
    CentralOrchestrator,
    InboxPacket,
    InboxStage,
    OrchestratorError,
    PlatformRegistration,
    RunLock,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def write_platform(root: Path, platform_id: str, *, foundry_root: Path = FOUNDRY) -> None:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "src" / "example.py").write_text("value = 1\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("# guide\n", encoding="utf-8")
    (root / "arkaon.workspace.json").write_text(
        json.dumps(
            {
                "schema_version": "arkaon.workspace/v1",
                "platform_id": platform_id,
                "foundry_root": str(foundry_root),
                "allowed_analysis_roots": ["src", "docs"],
                "forbidden_globs": [".env"],
                "production_change_allowed": False,
            }
        ),
        encoding="utf-8",
    )


def test_only_registered_platforms_are_analyzed(tmp_path: Path) -> None:
    platform = tmp_path / "demo-platform"
    write_platform(platform, "DEMO")
    orchestrator = CentralOrchestrator.from_config(FOUNDRY)
    report = orchestrator.run((PlatformRegistration("DEMO", platform),))
    assert report.production_change_allowed is False
    assert report.platform_reports[0].file_count >= 2
    assert (FOUNDRY / "inbox" / "research").exists()
    assert (FOUNDRY / "inbox" / "eternian-review").exists()


def test_unregistered_path_is_blocked_without_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing-platform"
    orchestrator = CentralOrchestrator.from_config(FOUNDRY)
    report = orchestrator.run((PlatformRegistration("MISSING", missing),))
    assert report.platform_reports[0].stage.value == "BLOCKED"


def test_shared_policy_rejects_operational_collection() -> None:
    bad = FOUNDRY / "config" / "shared-policy.json"
    original = bad.read_text(encoding="utf-8")
    document = json.loads(original)
    document["collect_platform_operational_data"] = True
    bad.write_text(json.dumps(document), encoding="utf-8")
    try:
        with pytest.raises(OrchestratorError) as caught:
            CentralOrchestrator.from_config(FOUNDRY)
        assert caught.value.code == "OPERATIONAL_DATA_FORBIDDEN"
    finally:
        bad.write_text(original, encoding="utf-8")


def test_platforms_json_must_match_foundry_root() -> None:
    registrations = CentralOrchestrator.load_platforms(
        FOUNDRY / "config" / "platforms.json",
        foundry_root=FOUNDRY,
    )
    assert registrations


def test_platforms_json_rejects_wrong_literal_foundry_root(tmp_path: Path) -> None:
    config = tmp_path / "platforms.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "apf.central-platforms/v1",
                "foundry_root": str(tmp_path / "other"),
                "platforms": [{"id": "DEMO", "path": str(tmp_path / "demo")}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(OrchestratorError) as caught:
        CentralOrchestrator.load_platforms(config, foundry_root=tmp_path)
    assert caught.value.code == "FOUNDRY_ROOT_MISMATCH"


def test_platform_id_mismatch_is_isolated(tmp_path: Path) -> None:
    platform = tmp_path / "demo-platform"
    write_platform(platform, "OTHER")
    orchestrator = CentralOrchestrator.from_config(FOUNDRY)
    report = orchestrator.run((PlatformRegistration("DEMO", platform),))
    assert report.platform_reports[0].stage.value == "BLOCKED"
    assert report.platform_reports[0].error_code == "PLATFORM_ID_MISMATCH"


def test_symlink_escape_is_skipped(tmp_path: Path) -> None:
    platform = tmp_path / "demo-platform"
    write_platform(platform, "DEMO")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    link = platform / "src" / "escape-link"
    if os.name == "nt":
        os.system(f'mklink "{link}" "{outside}"')
    else:
        link.symlink_to(outside)
    if not link.exists():
        pytest.skip("symlink creation unavailable")
    orchestrator = CentralOrchestrator.from_config(FOUNDRY)
    report = orchestrator.run((PlatformRegistration("DEMO", platform),))
    assert report.platform_reports[0].file_count == 2


def test_operator_decision_inbox_is_forbidden() -> None:
    orchestrator = CentralOrchestrator.from_config(FOUNDRY)
    with pytest.raises(OrchestratorError) as caught:
        orchestrator._write_inbox(
            InboxPacket(
                packet_id="demo-operator",
                stage=InboxStage.OPERATOR_DECISION,
                platform_id="DEMO",
                created_at=NOW,
                summary="demo",
            )
        )
    assert caught.value.code == "INBOX_STAGE_FORBIDDEN"


def test_run_lock_prevents_duplicate_execution(tmp_path: Path) -> None:
    lock_path = tmp_path / "orchestrator.run.lock"
    first = RunLock(lock_path)
    first.acquire()
    second = RunLock(lock_path)
    try:
        with pytest.raises(OrchestratorError) as caught:
            second.acquire()
        assert caught.value.code == "RUN_LOCK_HELD"
    finally:
        first.release()


def test_demo_map_ops_advisory_includes_map_ops_packet(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox", "reports", "logs", "state"):
        (foundry / folder).mkdir(parents=True, exist_ok=True)
    for name in (
        "shared-policy.json",
        "resource-limits.json",
        "arkaon-map-ops-gate.json",
        "map-competency-profile.json",
        "map-provider-knowledge.provisional.json",
    ):
        source = FOUNDRY / "config" / name
        if source.is_file():
            (foundry / "config" / name).write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8"
            )
    platform = tmp_path / "demo-platform"
    write_platform(platform, "DEMO", foundry_root=foundry)
    orchestrator = CentralOrchestrator.from_config(foundry)
    report = orchestrator.run(
        (PlatformRegistration("DEMO", platform),),
        dry_run=True,
        demo_map_ops_advisory=True,
    )
    from apf.central_orchestrator import classify_inbox_packet_path

    kinds = {classify_inbox_packet_path(path) for path in report.inbox_packets}
    assert "map_ops_gate" in kinds


def test_dry_run_reports_inbox_packet_plan(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox", "reports", "logs", "state"):
        (foundry / folder).mkdir(parents=True, exist_ok=True)
    for name in ("shared-policy.json", "resource-limits.json"):
        (foundry / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    platform = tmp_path / "demo-platform"
    write_platform(platform, "DEMO", foundry_root=foundry)
    orchestrator = CentralOrchestrator.from_config(foundry)
    report = orchestrator.run((PlatformRegistration("DEMO", platform),), dry_run=True)
    assert report.inbox_packets
    from apf.central_orchestrator import classify_inbox_packet_path

    kinds = {classify_inbox_packet_path(path) for path in report.inbox_packets}
    assert "platform_research" in kinds
    assert "platform_eternian_review" in kinds


def test_dry_run_writes_no_artifacts(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox", "reports", "logs", "state"):
        (foundry / folder).mkdir(parents=True, exist_ok=True)
    for name in ("shared-policy.json", "resource-limits.json"):
        (foundry / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    platform = tmp_path / "demo-platform"
    write_platform(platform, "DEMO", foundry_root=foundry)
    orchestrator = CentralOrchestrator.from_config(foundry)
    report = orchestrator.run((PlatformRegistration("DEMO", platform),), dry_run=True)
    assert report.platform_reports[0].file_count >= 1
    assert not any((foundry / "inbox" / "research").glob("*.json"))
    assert not any((foundry / "reports").rglob("*.json"))
    assert not (foundry / "state" / "orchestrator-state.json").exists()


def test_narang_workspace_id_matches_registration() -> None:
    workspace_path = Path("D:/narangrider/arkaon.workspace.json")
    if not workspace_path.is_file():
        pytest.skip("NARANG_RIDER workspace not present on this machine")
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    platforms = json.loads((FOUNDRY / "config" / "platforms.json").read_text(encoding="utf-8"))
    narang = next(item for item in platforms["platforms"] if item["id"] == "NARANG_RIDER")
    assert workspace["platform_id"] == narang["id"]


def make_isolated_foundry(tmp_path: Path) -> Path:
    foundry = tmp_path / "foundry"
    for folder in ("config", "inbox/research", "inbox/eternian-review", "reports", "logs", "state"):
        (foundry / folder).mkdir(parents=True, exist_ok=True)
    for name in ("shared-policy.json", "resource-limits.json"):
        (foundry / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return foundry


def test_equivalent_pending_packet_is_reused_instead_of_duplicated(tmp_path: Path) -> None:
    foundry = make_isolated_foundry(tmp_path)
    orchestrator = CentralOrchestrator.from_config(foundry)
    first = InboxPacket(
        packet_id="run-one-demo-research",
        stage=InboxStage.RESEARCH,
        platform_id="DEMO",
        created_at=NOW,
        summary="same intent and evidence",
        payload_digest="a" * 64,
    )
    second = InboxPacket(
        packet_id="run-two-demo-research",
        stage=InboxStage.RESEARCH,
        platform_id="DEMO",
        created_at=NOW,
        summary="same intent and evidence",
        payload_digest="a" * 64,
    )

    first_path = orchestrator._write_inbox(first)
    second_path = orchestrator._write_inbox(second)

    assert second_path == first_path
    assert len(list((foundry / "inbox" / "research").glob("*.json"))) == 1


def test_pending_limit_activates_single_backpressure_state(tmp_path: Path) -> None:
    foundry = make_isolated_foundry(tmp_path)
    (foundry / "config" / "resource-limits.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.resource-limits/v1",
                "max_platforms_per_run": 8,
                "max_files_per_platform": 5000,
                "max_inbox_packets": 2,
                "max_seconds_per_platform": 120,
                "max_memory_mb_per_platform": 512,
                "sequential_platform_analysis": True,
            }
        ),
        encoding="utf-8",
    )
    orchestrator = CentralOrchestrator.from_config(foundry)
    for index in range(orchestrator.limits.max_inbox_packets):
        (foundry / "inbox" / "research" / f"pending-{index}.json").write_text(
            json.dumps({"packet_id": f"pending-{index}"}),
            encoding="utf-8",
        )
    packet = InboxPacket(
        packet_id="blocked-new-packet",
        stage=InboxStage.ETHERNIAN_REVIEW,
        platform_id="DEMO",
        created_at=NOW,
        summary="new review request",
        payload_digest="b" * 64,
    )

    assert orchestrator._write_inbox(packet) is None
    assert not (foundry / "inbox" / "eternian-review" / "blocked-new-packet.json").exists()
    state_path = foundry / "state" / "inbox-backpressure.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "ACTIVE"
    assert state["pending_count"] == orchestrator.limits.max_inbox_packets
    assert state["new_packet_created"] is False
