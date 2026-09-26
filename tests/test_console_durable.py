from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from apf.acquisition_orchestrator import AcquisitionJob, AcquisitionJobRequest, JobState
from apf.api import create_app
from apf.authorized_material import MaterialRequest, UseRoute
from apf.console import ConsoleSecurity
from apf.durable_review import (
    DurableReviewRepository,
    ReviewDecision,
    ReviewSigner,
    ReviewStage,
)
from apf.repository import MemoryRepository

NOW = datetime(2031, 1, 1, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def make_job(tenant_id: UUID, principal_id: UUID) -> AcquisitionJob:
    correlation = uuid4()
    request = AcquisitionJobRequest(
        tenant_id=str(tenant_id), principal_id=str(principal_id),
        idempotency_key=str(uuid4()), correlation_id=correlation,
        material_request=MaterialRequest(
            source_url="https://example.com/app.js", allowed_origins=("https://example.com",),
            route=UseRoute.LICENSED_REUSE, purpose="authorized analysis",
            allowed_content_types=("application/javascript",), max_requests=2, max_bytes=1000,
            expires_at=LATER, correlation_id=str(correlation),
        ),
    )
    key = Ed25519PrivateKey.generate()
    return AcquisitionJob(
        request, ethernian_public_key=key.public_key(), mediator_public_key=key.public_key(),
        binding_public_key=key.public_key(), now_provider=lambda: NOW,
    )


def setup(tmp_path, *, role="reviewer"):
    private = Ed25519PrivateKey.generate()
    store = DurableReviewRepository(
        tmp_path / "console.sqlite", ethernian_public_key=private.public_key(),
        now_provider=lambda: NOW,
    )
    app = create_app(
        repository=MemoryRepository(), console_review_store=store,
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
    )
    client = TestClient(app, base_url="https://testserver")
    tenant_id, principal_id = uuid4(), uuid4()
    response = client.post("/console/dev/session", json={
        "tenant_id": str(tenant_id), "principal_id": str(principal_id), "role": role,
    })
    return client, store, private, tenant_id, principal_id, response.json()["csrf_token"]


def attestation_payload(item):
    value = asdict(item)
    value["stage"] = item.stage.value
    value["decision"] = item.decision.value
    value["expires_at"] = item.expires_at.isoformat()
    return value


def test_review_detail_is_principal_scoped(tmp_path):
    client, store, _, tenant, principal, _ = setup(tmp_path)
    record = store.create_job(make_job(tenant, principal))
    task = store.create_review(
        record.tenant_id, record.job_id, stage=ReviewStage.RIGHTS,
        reason_code="RIGHTS_CHECK", evidence_fingerprint="sha256:" + "1" * 64,
        expires_at=LATER,
    )
    response = client.get(f"/v1/console/reviews/{task.task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task.task_id
    assert body["request_fingerprint"] == record.request_fingerprint


def test_real_sqlite_reviews_are_principal_and_tenant_scoped_and_xss_is_inert(tmp_path):
    client, store, _, tenant, principal, _ = setup(tmp_path)
    own = store.create_job(make_job(tenant, principal))
    task = store.create_review(
        own.tenant_id, own.job_id, stage=ReviewStage.RIGHTS,
        reason_code="RIGHTS_CHECK", evidence_fingerprint="sha256:" + "1" * 64,
        expires_at=LATER,
    )
    other_principal = uuid4()
    other = store.create_job(make_job(tenant, other_principal))
    store.create_review(
        other.tenant_id, other.job_id, stage=ReviewStage.RIGHTS,
        reason_code="PRIVATE_CHECK", evidence_fingerprint="sha256:" + "2" * 64,
        expires_at=LATER,
    )
    other_tenant = uuid4()
    foreign = store.create_job(make_job(other_tenant, principal))
    store.create_review(
        foreign.tenant_id, foreign.job_id, stage=ReviewStage.RIGHTS,
        reason_code="FOREIGN_CHECK", evidence_fingerprint="sha256:" + "3" * 64,
        expires_at=LATER,
    )
    response = client.get("/v1/console/reviews")
    assert response.status_code == 200
    assert [item["task_id"] for item in response.json()] == [task.task_id]
    assert "PRIVATE_CHECK" not in response.text and "FOREIGN_CHECK" not in response.text
    assert "<script" not in response.text.lower()


def test_full_signed_decision_approval_tamper_replay_and_csrf(tmp_path):
    client, store, private, tenant, principal, csrf = setup(tmp_path)
    record = store.create_job(make_job(tenant, principal))
    task = store.create_review(
        record.tenant_id, record.job_id, stage=ReviewStage.ORIGINALITY,
        reason_code="ORIGINALITY_CHECK", evidence_fingerprint="sha256:" + "4" * 64,
        expires_at=LATER,
    )
    signed = ReviewSigner(private).sign(
        task, ReviewDecision.APPROVE, expires_at=LATER, nonce=str(uuid4())
    )
    url = f"/v1/console/reviews/{task.task_id}/decisions"
    assert client.post(url, json=attestation_payload(signed)).status_code == 403
    tampered = replace(signed, evidence_fingerprint="sha256:" + "9" * 64)
    assert client.post(
        url, json=attestation_payload(tampered), headers={"X-CSRF-Token": csrf}
    ).status_code == 403
    accepted = client.post(
        url, json=attestation_payload(signed), headers={"X-CSRF-Token": csrf}
    )
    assert accepted.status_code == 202 and accepted.json()["status"] == "APPROVED"
    assert client.post(
        url, json=attestation_payload(signed), headers={"X-CSRF-Token": csrf}
    ).status_code == 409


def test_denial_and_expired_attestation(tmp_path):
    client, store, private, tenant, principal, csrf = setup(tmp_path)
    first = store.create_job(make_job(tenant, principal))
    denied_task = store.create_review(
        first.tenant_id, first.job_id, stage=ReviewStage.COLLECTION,
        reason_code="COLLECTION_CHECK", evidence_fingerprint="sha256:" + "5" * 64,
        expires_at=LATER,
    )
    denied = ReviewSigner(private).sign(
        denied_task, ReviewDecision.DENY, expires_at=LATER, nonce=str(uuid4())
    )
    response = client.post(
        f"/v1/console/reviews/{denied_task.task_id}/decisions",
        json=attestation_payload(denied), headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 202 and response.json()["status"] == "DENIED"

    second = store.create_job(make_job(tenant, principal))
    task = store.create_review(
        second.tenant_id, second.job_id, stage=ReviewStage.RIGHTS,
        reason_code="RIGHTS_CHECK", evidence_fingerprint="sha256:" + "6" * 64,
        expires_at=LATER,
    )
    expired = ReviewSigner(private).sign(
        task, ReviewDecision.APPROVE, expires_at=NOW, nonce=str(uuid4())
    )
    assert client.post(
        f"/v1/console/reviews/{task.task_id}/decisions",
        json=attestation_payload(expired), headers={"X-CSRF-Token": csrf},
    ).status_code == 422


def test_candidate_listing_is_safe_deterministic_and_tenant_scoped(tmp_path):
    client, store, _, tenant, principal, _ = setup(tmp_path)
    job = make_job(tenant, principal)
    record = store.create_job(job)
    job.state = JobState.ASSET_CANDIDATE
    job.version += 1
    job._append("ASSET_CANDIDATE_CREATED", {"payload_fingerprint": "sha256:" + "a" * 64})
    store.save_job(job, expected_version=0)
    store.put_candidate_manifest(
        record.tenant_id, record.job_id, candidate_hash="sha256:" + "7" * 64,
        quarantine_reference=f"quarantine:{uuid4()}",
        license_obligations=("SOURCE_DISCLOSURE", "ATTRIBUTION", "ATTRIBUTION"),
    )
    response = client.get("/v1/console/candidates?limit=1&offset=0")
    assert response.status_code == 200
    assert response.json() == [{
        "job_fingerprint": record.job_fingerprint, "candidate_hash": "sha256:" + "7" * 64,
        "license_obligations": ["ATTRIBUTION", "SOURCE_DISCLOSURE"],
        "status": "CANDIDATE_NOT_OWNED_ASSET",
    }]
    for forbidden in ("quarantine", "signature", "principal", "raw"):
        assert forbidden not in response.text.lower()
    assert client.get("/v1/console/candidates?limit=101").status_code == 422


def test_unavailable_store_fails_closed_instead_of_empty_success(tmp_path):
    client, store, _, _, _, _ = setup(tmp_path)
    store.path = str(tmp_path / "missing" / "cannot-open.sqlite")
    assert client.get("/v1/console/reviews").status_code == 503
    assert client.get("/v1/console/candidates").status_code == 503
