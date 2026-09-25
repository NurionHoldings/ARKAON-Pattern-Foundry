from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from apf.api import create_app
from apf.github_owner_auth import GitHubOwnerAuth
from apf.production_readiness import production_ready
from apf.repository import MemoryRepository, PostgresRepository


def test_production_readiness_fails_closed_without_postgres(monkeypatch):
    monkeypatch.setenv("APF_ENV", "production")
    assert production_ready(MemoryRepository()) is False


def test_ready_endpoint_does_not_report_process_health_as_operational_readiness(monkeypatch):
    monkeypatch.setenv("APF_ENV", "development")
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_production_readiness_requires_migration_ledger_and_tenant(monkeypatch, tmp_path):
    import apf.production_readiness as readiness

    tenant_id = uuid4()
    engine = create_engine("sqlite://", poolclass=StaticPool)
    repo = PostgresRepository(engine=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE tenants (id TEXT PRIMARY KEY)")
    monkeypatch.setenv("APF_ENV", "production")
    monkeypatch.setenv("APF_TENANT_ID", str(tenant_id))
    monkeypatch.setenv("APF_RUNTIME_ROOT", "/data/runtime")
    monkeypatch.setenv("APF_FOUNDRY_ROOT", "/data/foundry")
    monkeypatch.setattr(Path, "is_mount", lambda self: str(self) == "/data")
    monkeypatch.setattr(Path, "is_dir", lambda self: str(self).startswith("/data/"))
    monkeypatch.setattr(GitHubOwnerAuth, "from_environment", lambda: object())
    monkeypatch.setattr(readiness, "migration_versions", lambda: ("0001_core",))
    assert production_ready(repo) is False
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO schema_migrations VALUES ('0001_core')")
    assert production_ready(repo) is False
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO tenants VALUES (?)", (str(tenant_id),))
    assert production_ready(repo) is True
