import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.postgres_live_proof import (
    PostgresLiveProofHarness,
    PostgresLiveProofRejected,
    ProofStatus,
    redact_database_url,
    resolve_database_url,
)

ROOT = Path(__file__).parents[1]
DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")


def test_redact_database_url_masks_credentials():
    assert redact_database_url("postgresql+psycopg://user:secret@localhost/db") == "postgresql+psycopg://***@localhost/db"


def test_resolve_database_url_prefers_test_env(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://other")
    assert resolve_database_url() == "postgresql://test"


def test_live_proof_skips_without_database_url(monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    report = PostgresLiveProofHarness(foundry_root=tmp_path).run(
        now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=True
    )
    assert report.overall is ProofStatus.SKIP
    assert report.results[0].check_id == "DATABASE_URL"


def test_live_proof_passes_on_postgres():
    report = PostgresLiveProofHarness(foundry_root=ROOT).run(
        now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=True
    )
    assert report.overall is ProofStatus.PASS
    check_ids = {item.check_id for item in report.results}
    assert {
        "MIGRATION_DOWNGRADE",
        "MIGRATION_UPGRADE",
        "REPOSITORY_CONTRACT",
        "DURABLE_SCHEMA",
    } <= check_ids


def test_live_proof_writes_report_when_not_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", DATABASE_URL)
    harness = PostgresLiveProofHarness(foundry_root=tmp_path)
    harness.run(now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=False)
    assert list((tmp_path / "state" / "postgres-live-proof").glob("*.json"))


def test_live_proof_raises_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://invalid:invalid@127.0.0.1:1/none")
    with pytest.raises(PostgresLiveProofRejected) as error:
        PostgresLiveProofHarness(foundry_root=tmp_path).run(
            now=datetime(2031, 1, 1, tzinfo=UTC), dry_run=True
        )
    assert error.value.code == "POSTGRES_LIVE_PROOF_FAILED"
