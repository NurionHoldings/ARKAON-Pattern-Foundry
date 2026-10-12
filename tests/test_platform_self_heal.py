import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import ConsoleSecurity
from apf.platform_self_heal import (
    PlatformSelfHealRejected,
    assess_static_platform,
    ingest_surface_report,
)
from apf.repository import MemoryRepository
from tests.test_console import make_client


def test_ingest_writes_inbox_and_syncs_mailbox(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "arkaon-platform-self-heal.json").write_text(
        '{"schema_version":"apf.platform-self-heal/v1","platform_id":"ARKAON_FOUNDRY",'
        '"beom_assignee_gap_codes":["API_HEALTH_MISSING"],"eternian_assignee_gap_codes":[]}',
        encoding="utf-8",
    )
    (tmp_path / "config" / "arkaon-home-services.json").write_text(
        '{"schema_version":"apf.home-services/v1","services":[]}',
        encoding="utf-8",
    )
    now = datetime(2026, 10, 12, tzinfo=UTC)
    result = ingest_surface_report(
        foundry_root=tmp_path,
        platform_id="ARKAON_FOUNDRY",
        surface_url="https://example.test/",
        finding_payloads=(
            {
                "gap_code": "API_HEALTH_MISSING",
                "severity": "BLOCKER",
                "summary": "Foundry /health unreachable",
                "needed_from_admin": "Start API or configure proxy",
            },
        ),
        now=now,
        include_static_assessment=False,
    )
    inbox = tmp_path / "inbox" / "research"
    paths = list(inbox.glob("*-platform-self-heal-research.json"))
    assert len(paths) == 1
    assert result["finding_count"] >= 1
    assert (tmp_path / "state" / "mailbox" / "items").is_dir()


def test_assess_flags_missing_service_path(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "arkaon-platform-self-heal.json").write_text(
        '{"schema_version":"apf.platform-self-heal/v1","platform_id":"ARKAON_FOUNDRY"}',
        encoding="utf-8",
    )
    (tmp_path / "config" / "arkaon-home-services.json").write_text(
        '{"schema_version":"apf.home-services/v1","services":[{"id":"x","title":"X",'
        '"status":"available","href":"/services/missing.html"}]}',
        encoding="utf-8",
    )
    findings = assess_static_platform(tmp_path)
    assert any(f.gap_code == "BROKEN_SERVICE_PATH" for f in findings)


def _seed_self_heal_config(tmp_path: Path) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    for name in (
        "arkaon-platform-self-heal.json",
        "arkaon-home-services.json",
        "arkaon-public-api.json",
    ):
        shutil.copy(repo_config / name, tmp_path / "config" / name)


def test_console_self_heal_surface_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_self_heal_config(tmp_path)
    monkeypatch.setenv("APF_FOUNDRY_ROOT", str(tmp_path))
    client, _, _, csrf = make_client()
    payload = {
        "platform_id": "ARKAON_FOUNDRY",
        "surface_url": "https://testserver/",
        "include_static_assessment": False,
        "findings": [
            {
                "gap_code": "API_HEALTH_MISSING",
                "severity": "BLOCKER",
                "summary": "health down",
                "needed_from_admin": "start api",
            }
        ],
    }
    response = client.post(
        "/v1/console/platform-self-heal/surface-report",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert list((tmp_path / "inbox" / "research").glob("*-platform-self-heal-research.json"))


def test_public_self_heal_hidden_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_self_heal_config(tmp_path)
    monkeypatch.setenv("APF_FOUNDRY_ROOT", str(tmp_path))
    monkeypatch.delenv("APF_ALLOW_PUBLIC_SELF_HEAL", raising=False)
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
    )
    client = TestClient(app, base_url="https://testserver")
    response = client.post(
        "/v1/public/platform-self-heal",
        json={
            "surface_url": "https://test/",
            "findings": [
                {
                    "gap_code": "API_HEALTH_MISSING",
                    "severity": "BLOCKER",
                    "summary": "x",
                    "needed_from_admin": "y",
                }
            ],
        },
    )
    assert response.status_code == 404


def test_rejects_empty_findings(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "arkaon-platform-self-heal.json").write_text(
        '{"schema_version":"apf.platform-self-heal/v1","platform_id":"ARKAON_FOUNDRY"}',
        encoding="utf-8",
    )
    with pytest.raises(PlatformSelfHealRejected):
        ingest_surface_report(
            foundry_root=tmp_path,
            platform_id="ARKAON_FOUNDRY",
            surface_url="https://example.test/",
            finding_payloads=(),
            now=datetime(2026, 10, 12, tzinfo=UTC),
            include_static_assessment=False,
        )
