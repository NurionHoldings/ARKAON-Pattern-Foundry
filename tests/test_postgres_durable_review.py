import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine

from apf.acquisition_orchestrator import AcquisitionJob, AcquisitionJobRequest
from apf.authorized_material import MaterialRequest, UseRoute
from apf.durable_review import DurableStoreError, ReviewDecision, ReviewSigner, ReviewStage
from apf.migrations import downgrade, upgrade
from apf.postgres_durable_review import PostgresDurableReviewRepository

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")

NOW = datetime(2031, 1, 1, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


@pytest.fixture()
def postgres_review_store():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    downgrade(engine)
    upgrade(engine)
    private = Ed25519PrivateKey.generate()
    store = PostgresDurableReviewRepository(
        engine, ethernian_public_key=private.public_key(), now_provider=lambda: NOW
    )
    yield store, private
    downgrade(engine)
    engine.dispose()


def make_job(tenant_id: UUID, principal_id: UUID) -> AcquisitionJob:
    correlation = uuid4()
    request = AcquisitionJobRequest(
        tenant_id=str(tenant_id),
        principal_id=str(principal_id),
        idempotency_key=str(uuid4()),
        correlation_id=correlation,
        material_request=MaterialRequest(
            source_url="https://example.com/app.js",
            allowed_origins=("https://example.com",),
            route=UseRoute.LICENSED_REUSE,
            purpose="authorized analysis",
            allowed_content_types=("application/javascript",),
            max_requests=2,
            max_bytes=1000,
            expires_at=LATER,
            correlation_id=str(correlation),
        ),
    )
    key = Ed25519PrivateKey.generate()
    return AcquisitionJob(
        request,
        ethernian_public_key=key.public_key(),
        mediator_public_key=key.public_key(),
        binding_public_key=key.public_key(),
        now_provider=lambda: NOW,
    )


def test_postgres_durable_review_create_list_get_and_decide(postgres_review_store):
    store, private = postgres_review_store
    tenant_id, principal_id = uuid4(), uuid4()
    record = store.create_job(make_job(tenant_id, principal_id))
    task = store.create_review(
        record.tenant_id,
        record.job_id,
        stage=ReviewStage.RIGHTS,
        reason_code="RIGHTS_CHECK",
        evidence_fingerprint="sha256:" + "1" * 64,
        expires_at=LATER,
    )
    assert store.count_reviews_for_principal(str(tenant_id), str(principal_id)) == 1
    listed = store.list_reviews_for_principal(str(tenant_id), str(principal_id), limit=10, offset=0)
    assert [item.task_id for item in listed] == [task.task_id]
    fetched = store.get_review_for_principal(str(tenant_id), str(principal_id), task.task_id)
    assert fetched.reason_code == "RIGHTS_CHECK"
    signed = ReviewSigner(private).sign(task, ReviewDecision.APPROVE, expires_at=LATER, nonce=str(uuid4()))
    decided = store.decide_review(str(tenant_id), task.task_id, signed)
    assert decided.status.value == "APPROVED"


def test_postgres_durable_review_principal_scope(postgres_review_store):
    store, _ = postgres_review_store
    tenant_id, principal_id = uuid4(), uuid4()
    record = store.create_job(make_job(tenant_id, principal_id))
    task = store.create_review(
        record.tenant_id,
        record.job_id,
        stage=ReviewStage.ORIGINALITY,
        reason_code="ORIGINALITY_CHECK",
        evidence_fingerprint="sha256:" + "2" * 64,
        expires_at=LATER,
    )
    with pytest.raises(DurableStoreError, match="REVIEW_NOT_FOUND"):
        store.get_review_for_principal(str(tenant_id), str(uuid4()), task.task_id)
