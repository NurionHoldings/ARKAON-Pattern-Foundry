from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.acquisition_orchestrator import (
    AcquisitionJob,
    AcquisitionJobRequest,
    JobState,
    _hash,
    _time,
)
from apf.authorized_material import MaterialRequest, UseRoute
from apf.durable_review import (
    DurableReviewRepository,
    DurableStoreError,
    ReviewDecision,
    ReviewSigner,
    ReviewStage,
    ReviewStatus,
)

NOW = datetime(2031, 1, 1, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def make_job(*, tenant="tenant-a", idempotency="idem-a"):
    correlation = uuid4()
    request = AcquisitionJobRequest(
        tenant_id=tenant,
        principal_id="principal-a",
        idempotency_key=idempotency,
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
    job = AcquisitionJob(
        request,
        ethernian_public_key=key.public_key(),
        mediator_public_key=key.public_key(),
        binding_public_key=key.public_key(),
        now_provider=lambda: NOW,
    )
    return job


@pytest.fixture
def store(tmp_path):
    key = Ed25519PrivateKey.generate()
    return DurableReviewRepository(
        tmp_path / "durable.sqlite", ethernian_public_key=key.public_key(),
        now_provider=lambda: NOW,
    ), key


def test_persists_and_reopens_without_raw_material(store):
    repo, key = store
    job = make_job()
    created = repo.create_job(job)
    reopened = DurableReviewRepository(repo.path, ethernian_public_key=key.public_key(), now_provider=lambda: NOW)
    loaded = reopened.load_job("tenant-a", created.job_id)
    assert loaded == created
    data = Path(repo.path).read_bytes()
    assert b"function" not in data and b"app.js" not in data


def test_save_is_optimistic_and_receipts_are_idempotent(store):
    repo, _ = store
    job = make_job()
    repo.create_job(job)
    receipt = job.start("start", 0)
    saved = repo.save_job(job, expected_version=0)
    assert saved.version == 1
    assert repo.get_command_receipt(
        "tenant-a", saved.job_id, "start", receipt.payload_fingerprint
    )["resulting_version"] == 1
    with pytest.raises(DurableStoreError, match="IDEMPOTENCY_CONFLICT"):
        repo.get_command_receipt("tenant-a", saved.job_id, "start", "sha256:" + "9" * 64)
    with pytest.raises(DurableStoreError, match="STALE_VERSION"):
        repo.save_job(job, expected_version=0)


def test_concurrent_writers_only_one_commits(store):
    repo, _ = store
    job = make_job()
    repo.create_job(job)
    job.start("start", 0)

    def save():
        try:
            repo.save_job(job, expected_version=0)
            return "OK"
        except DurableStoreError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: save(), range(2)))
    assert sorted(outcomes) == ["OK", "STALE_VERSION"]


def test_create_idempotency_and_cross_tenant_isolation(store):
    repo, _ = store
    first = make_job()
    record = repo.create_job(first)
    retry = make_job(idempotency="idem-a")
    # Same idempotency key with a different canonical request is a conflict.
    with pytest.raises(DurableStoreError, match="IDEMPOTENCY_CONFLICT"):
        repo.create_job(retry)
    with pytest.raises(DurableStoreError, match="JOB_NOT_FOUND"):
        repo.load_job("tenant-b", record.job_id)


@pytest.mark.parametrize("attack", ["modify", "delete", "transplant", "snapshot"])
def test_load_detects_database_tampering(store, attack):
    repo, _ = store
    first = make_job()
    record = repo.create_job(first)
    second = make_job(tenant="tenant-b", idempotency="idem-b")
    other = repo.create_job(second)
    with repo._connect() as db:
        if attack == "modify":
            db.execute(
                "UPDATE durable_events SET event_type='JOB_STARTED' WHERE tenant_id=? AND job_id=?",
                (record.tenant_id, record.job_id),
            )
        elif attack == "delete":
            db.execute(
                "DELETE FROM durable_events WHERE tenant_id=? AND job_id=?",
                (record.tenant_id, record.job_id),
            )
        elif attack == "transplant":
            db.execute(
                "UPDATE durable_events SET job_fingerprint=? WHERE tenant_id=? AND job_id=?",
                (other.job_fingerprint, record.tenant_id, record.job_id),
            )
        else:
            db.execute(
                "UPDATE durable_jobs SET state='RIGHTS_REVIEW' WHERE tenant_id=? AND job_id=?",
                (record.tenant_id, record.job_id),
            )
    with pytest.raises(DurableStoreError, match="INTEGRITY|MISMATCH"):
        repo.load_job(record.tenant_id, record.job_id)


def test_signed_review_approval_and_denial_unlock_only_review(store):
    repo, private = store
    job = make_job()
    record = repo.create_job(job)
    task = repo.create_review(
        record.tenant_id, record.job_id, stage=ReviewStage.RIGHTS,
        reason_code="RIGHTS_CHECK", evidence_fingerprint="sha256:" + "1" * 64,
        expires_at=LATER,
    )
    signed = ReviewSigner(private).sign(
        task, ReviewDecision.APPROVE, expires_at=LATER, nonce=str(uuid4())
    )
    closed = repo.decide_review(record.tenant_id, task.task_id, signed)
    assert closed.status is ReviewStatus.APPROVED
    assert repo.load_job(record.tenant_id, record.job_id).state is JobState.QUEUED
    with pytest.raises(DurableStoreError, match="ALREADY_CLOSED"):
        repo.decide_review(record.tenant_id, task.task_id, signed)


def test_closed_review_signature_is_reverified_on_restart(store):
    repo, private = store
    record = repo.create_job(make_job())
    task = repo.create_review(
        record.tenant_id, record.job_id, stage=ReviewStage.ORIGINALITY,
        reason_code="ORIGINALITY_CHECK", evidence_fingerprint="sha256:" + "8" * 64,
        expires_at=LATER,
    )
    signed = ReviewSigner(private).sign(
        task, ReviewDecision.APPROVE, expires_at=LATER, nonce=str(uuid4())
    )
    repo.decide_review(record.tenant_id, task.task_id, signed)
    with repo._connect() as db:
        db.execute(
            "UPDATE review_tasks SET decision_signature=? WHERE tenant_id=? AND task_id=?",
            ("00" * 64, record.tenant_id, task.task_id),
        )
    with pytest.raises(DurableStoreError, match="REVIEW_INTEGRITY_FAILURE"):
        repo.load_job(record.tenant_id, record.job_id)


@pytest.mark.parametrize("field", ["stage", "reason_code", "evidence_fingerprint", "expires_at"])
def test_open_review_immutable_fields_are_verified(store, field):
    repo, _ = store
    record = repo.create_job(make_job())
    task = repo.create_review(
        record.tenant_id, record.job_id, stage=ReviewStage.RIGHTS,
        reason_code="RIGHTS_CHECK", evidence_fingerprint="sha256:" + "b" * 64,
        expires_at=LATER,
    )
    changed = {
        "stage": "COLLECTION",
        "reason_code": "ALTERED_REASON",
        "evidence_fingerprint": "sha256:" + "c" * 64,
        "expires_at": (LATER + timedelta(minutes=1)).isoformat(timespec="microseconds"),
    }[field]
    with repo._connect() as db:
        db.execute(
            f"UPDATE review_tasks SET {field}=? WHERE tenant_id=? AND task_id=?",
            (changed, record.tenant_id, task.task_id),
        )
    with pytest.raises(DurableStoreError, match="REVIEW_INTEGRITY_FAILURE"):
        repo.load_job(record.tenant_id, record.job_id)


@pytest.mark.parametrize("failure", ["tamper", "wrong_task", "wrong_key", "expired"])
def test_review_attestation_fail_closed(store, failure):
    repo, private = store
    job = make_job()
    record = repo.create_job(job)
    task = repo.create_review(
        record.tenant_id, record.job_id, stage=ReviewStage.COLLECTION,
        reason_code="COLLECTION_CHECK", evidence_fingerprint="sha256:" + "2" * 64,
        expires_at=LATER,
    )
    signer = ReviewSigner(Ed25519PrivateKey.generate() if failure == "wrong_key" else private)
    signed = signer.sign(
        task, ReviewDecision.DENY,
        expires_at=(NOW - timedelta(seconds=1) if failure == "expired" else LATER),
        nonce=str(uuid4()),
    )
    if failure == "tamper":
        signed = replace(signed, evidence_fingerprint="sha256:" + "3" * 64)
    elif failure == "wrong_task":
        signed = replace(signed, task_id=str(uuid4()))
    with pytest.raises(DurableStoreError):
        repo.decide_review(record.tenant_id, task.task_id, signed)
    assert repo.list_open_reviews(record.tenant_id, record.job_id) == (task,)


def test_review_nonce_cannot_cross_tasks(store):
    repo, private = store
    record = repo.create_job(make_job())
    tasks = [repo.create_review(
        record.tenant_id, record.job_id, stage=stage, reason_code="CHECK_REQUIRED",
        evidence_fingerprint="sha256:" + digit * 64, expires_at=LATER,
    ) for stage, digit in ((ReviewStage.RIGHTS, "4"), (ReviewStage.ORIGINALITY, "5"))]
    nonce = str(uuid4())
    signer = ReviewSigner(private)
    repo.decide_review(record.tenant_id, tasks[0].task_id,
                       signer.sign(tasks[0], ReviewDecision.APPROVE, expires_at=LATER, nonce=nonce))
    with pytest.raises(DurableStoreError, match="NONCE_REPLAY"):
        repo.decide_review(record.tenant_id, tasks[1].task_id,
                           signer.sign(tasks[1], ReviewDecision.APPROVE, expires_at=LATER, nonce=nonce))


def test_expired_review_is_closed_on_restart(tmp_path):
    clock = {"now": NOW}
    private = Ed25519PrivateKey.generate()
    repo = DurableReviewRepository(
        tmp_path / "expiry.sqlite", ethernian_public_key=private.public_key(),
        now_provider=lambda: clock["now"],
    )
    record = repo.create_job(make_job())
    task = repo.create_review(
        record.tenant_id, record.job_id, stage=ReviewStage.RIGHTS,
        reason_code="RIGHTS_CHECK", evidence_fingerprint="sha256:" + "6" * 64,
        expires_at=NOW + timedelta(minutes=1),
    )
    clock["now"] = NOW + timedelta(minutes=2)
    assert repo.list_open_reviews(record.tenant_id, record.job_id) == ()
    with repo._connect() as db:
        status = db.execute("SELECT status FROM review_tasks WHERE task_id=?", (task.task_id,)).fetchone()[0]
    assert status == "EXPIRED"


def test_candidate_manifest_never_promotes_owned_asset(store):
    repo, _ = store
    job = make_job()
    record = repo.create_job(job)
    with pytest.raises(DurableStoreError, match="CANDIDATE_STATE_REQUIRED"):
        repo.put_candidate_manifest(
            record.tenant_id, record.job_id, candidate_hash="sha256:" + "7" * 64,
            quarantine_reference=f"quarantine:{uuid4()}", license_obligations=("ATTRIBUTION",),
        )
    job.state = JobState.ASSET_CANDIDATE
    job.version += 1
    job._append("ASSET_CANDIDATE_CREATED", {"payload_fingerprint": "sha256:" + "a" * 64})
    repo.save_job(job, expected_version=0)
    repo.put_candidate_manifest(
        record.tenant_id, record.job_id, candidate_hash="sha256:" + "7" * 64,
        quarantine_reference=f"quarantine:{uuid4()}", license_obligations=("ATTRIBUTION",),
    )
    with repo._connect() as db:
        row = db.execute(
            "SELECT status,license_obligations FROM candidate_manifests"
        ).fetchone()
    assert tuple(row) == ("CANDIDATE_NOT_OWNED_ASSET", '["ATTRIBUTION"]')


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("candidate_hash", "sha256:" + "d" * 64),
        ("quarantine_reference", f"quarantine:{uuid4()}"),
        ("license_obligations", '["SOURCE_DISCLOSURE"]'),
        ("status", "OWNED_ASSET"),
        ("job_event_head", "sha256:" + "e" * 64),
    ],
)
def test_candidate_manifest_tamper_is_detected(store, field, changed):
    repo, _ = store
    job = make_job()
    record = repo.create_job(job)
    job.state = JobState.ASSET_CANDIDATE
    job.version += 1
    job._append("ASSET_CANDIDATE_CREATED", {"payload_fingerprint": "sha256:" + "a" * 64})
    repo.save_job(job, expected_version=0)
    repo.put_candidate_manifest(
        record.tenant_id, record.job_id, candidate_hash="sha256:" + "7" * 64,
        quarantine_reference=f"quarantine:{uuid4()}", license_obligations=("ATTRIBUTION",),
    )
    with repo._connect() as db:
        if field == "status":
            db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(
            f"UPDATE candidate_manifests SET {field}=? WHERE tenant_id=? AND job_id=?",
            (changed, record.tenant_id, record.job_id),
        )
    with pytest.raises(DurableStoreError, match="CANDIDATE_INTEGRITY_FAILURE"):
        repo.load_job(record.tenant_id, record.job_id)


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("command_id", "altered-command"),
        ("payload_fingerprint", "sha256:" + "f" * 64),
        ("resulting_state", "QUEUED"),
        ("resulting_version", 99),
        ("event_hash", "sha256:" + "0" * 64),
        ("receipt_hash", "sha256:" + "1" * 64),
    ],
)
def test_command_receipt_tamper_is_detected(store, field, changed):
    repo, _ = store
    job = make_job()
    record = repo.create_job(job)
    job.start("start", 0)
    repo.save_job(job, expected_version=0)
    with repo._connect() as db:
        db.execute(
            f"UPDATE command_receipts SET {field}=? WHERE tenant_id=? AND job_id=?",
            (changed, record.tenant_id, record.job_id),
        )
    with pytest.raises(DurableStoreError, match="RECEIPT_INTEGRITY_FAILURE"):
        repo.load_job(record.tenant_id, record.job_id)


def test_persistence_boundary_rejects_secret_metadata(store):
    repo, _ = store
    job = make_job()
    repo.create_job(job)
    job.start("start", 0)
    event = job.events[-1]
    metadata = {"session_token": "Bearer abcdefghijklmnop"}
    body = {
        "event_type": event.event_type, "job_fingerprint": event.job_fingerprint,
        "metadata": metadata, "previous_hash": event.previous_hash,
        "sequence": event.sequence, "state": event.state.value,
        "timestamp": _time(event.timestamp), "version": event.version,
    }
    job.events[-1] = replace(event, metadata=metadata, event_hash=_hash(body))
    with pytest.raises(DurableStoreError, match="FORBIDDEN_PERSISTED_FIELD"):
        repo.save_job(job, expected_version=0)
