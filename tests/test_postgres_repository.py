import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from test_repository_contract import assert_repository_contract, make_value

from apf.domain import TargetState
from apf.migrations import downgrade, upgrade
from apf.repository import PostgresRepository, RevisionConflict

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")


@pytest.fixture()
def postgres_repository():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    downgrade(engine)
    assert upgrade(engine) == ("0001_core", "0002_target_repository", "0003_durable_review")
    repository = PostgresRepository(engine=engine)
    yield repository
    downgrade(engine)
    engine.dispose()


def test_upgrade_repository_contract_and_downgrade(postgres_repository):
    tenant_id = uuid4()
    postgres_repository.provision_tenant(tenant_id, f"tenant-{tenant_id}")
    assert_repository_contract(postgres_repository, tenant_id)


def test_optimistic_revision_allows_exactly_one_concurrent_writer(postgres_repository):
    tenant_id = uuid4()
    postgres_repository.provision_tenant(tenant_id, f"tenant-{tenant_id}")
    target = postgres_repository.create_target(make_value(tenant_id, name="race"))

    def move():
        try:
            return postgres_repository.set_target_state(
                target.id, tenant_id, 0, TargetState.AUTHORIZATION_PENDING
            ).revision
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: move(), range(2)))
    assert sorted(results, key=str) == [1, "conflict"]


def test_concurrent_idempotent_creates_converge(postgres_repository):
    tenant_id = uuid4()
    postgres_repository.provision_tenant(tenant_id, f"tenant-{tenant_id}")
    value = make_value(tenant_id, name="idempotency-race")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: postgres_repository.create_target(value), range(2)))
    assert results[0].id == results[1].id


def test_json_is_round_tripped_and_tenant_fk_is_enforced(postgres_repository):
    tenant_id = uuid4()
    postgres_repository.provision_tenant(tenant_id, f"tenant-{tenant_id}")
    value = make_value(tenant_id, name="canonical-json")
    target = postgres_repository.create_target(value)
    restored = postgres_repository.get_target(target.id, tenant_id)
    assert restored.permissions == value.permissions
    assert restored.source_evidence_ids == value.source_evidence_ids

    with postgres_repository._engine.connect() as connection:
        stored = connection.execute(
            text("SELECT jsonb_typeof(permissions_json), jsonb_typeof(source_evidence_ids_json) "
                 "FROM analysis_targets WHERE id=:id"),
            {"id": target.id},
        ).one()
    assert stored == ("object", "array")
