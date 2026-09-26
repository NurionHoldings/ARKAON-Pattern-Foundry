from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.acquisition_orchestrator import (
    AcquisitionJob,
    AcquisitionJobRequest,
    JobBindingSigner,
    JobError,
    JobState,
    SanitizedInputEnvelope,
)
from apf.authorized_material import (
    CollectionPosture,
    EthernianSigner,
    ImprovementEvidence,
    LicenseTerms,
    MaterialRequest,
    ReviewDecision,
    RightsEvidence,
    SanitizedCapture,
    SourceRights,
    UseRoute,
    originality_payload_fingerprint,
)
from apf.mediated_auth import (
    AttestationSigner,
    AuthMethod,
    AuthRequest,
    OpaqueGrant,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def material(correlation_id, route=UseRoute.LICENSED_REUSE):
    return MaterialRequest(
        source_url="https://example.com/app.js",
        allowed_origins=("https://example.com",),
        route=route,
        purpose="authorized analysis",
        allowed_content_types=("application/javascript",),
        max_requests=2,
        max_bytes=10000,
        expires_at=LATER,
        correlation_id=str(correlation_id),
    )


def auth(correlation_id, actions=()):
    return AuthRequest(
        service_origin="https://example.com",
        purpose="authorized analysis",
        scopes=("read",),
        read_only=True,
        expected_asset_types=("javascript",),
        public_source_gap="authorized private workspace",
        terms_and_license="owner permission",
        risks=("privacy",),
        expires_at=LATER,
        correlation_id=correlation_id,
        auth_method=AuthMethod.BROWSER_AUTH,
        user_actions=actions,
    )


def setup(route=UseRoute.LICENSED_REUSE, with_auth=False, actions=()):
    correlation = uuid4()
    request = AcquisitionJobRequest(
        tenant_id="tenant-a",
        principal_id="principal-a",
        idempotency_key="job-one",
        correlation_id=correlation,
        material_request=material(correlation, route),
        auth_request=auth(correlation, actions) if with_auth else None,
    )
    ethernian = Ed25519PrivateKey.generate()
    mediator = Ed25519PrivateKey.generate()
    binder = Ed25519PrivateKey.generate()
    job = AcquisitionJob(
        request,
        ethernian_public_key=ethernian.public_key(),
        mediator_public_key=mediator.public_key(),
        binding_public_key=binder.public_key(),
        now_provider=lambda: NOW,
    )
    return job, EthernianSigner(ethernian), AttestationSigner(ethernian), AttestationSigner(mediator), JobBindingSigner(binder)


def evidence():
    return RightsEvidence(
        SourceRights.PERMISSIVE_LICENSE,
        "sha256:" + "1" * 64,
        LicenseTerms("MIT", True, True, True),
        "example owner",
    )


def advance_to_capture(job, es, bs):
    job.start("start", 0)
    rights = evidence()
    right_att = es.sign(
        job.request.material_request, rights, stage="RIGHTS",
        stage_payload_fingerprint=rights.fingerprint, decision=ReviewDecision.APPROVE,
        expires_at=LATER, nonce=str(uuid4()),
    )
    job.review_rights(
        "rights", 1, rights, right_att,
        bs.sign(job.request, stage="RIGHTS", evidence=right_att, expires_at=LATER, nonce=str(uuid4())),
    )
    posture = CollectionPosture("ALLOW", "OK")
    collection_att = es.sign(
        job.request.material_request, rights, stage="COLLECTION_POLICY",
        stage_payload_fingerprint=posture.fingerprint, decision=ReviewDecision.APPROVE,
        expires_at=LATER, nonce=str(uuid4()),
    )
    job.review_collection(
        "collection", 2, posture, collection_att,
        bs.sign(job.request, stage="COLLECTION", evidence=collection_att, expires_at=LATER, nonce=str(uuid4())),
    )
    return rights


def envelope():
    capture = SanitizedCapture(
        "https://example.com/app.js", "application/javascript",
        "function sum(a,b){return a+b}", None, None, None, "sha256:" + "2" * 64,
    )
    return SanitizedInputEnvelope(capture, f"quarantine:{uuid4()}", "sha256:" + "3" * 64)


def finish(job, es, bs, rights, candidate="function improved(x,y){return Number(x)+Number(y)}"):
    item = envelope()
    job.accept_sanitized_input(
        "capture", 3, item,
        bs.sign(job.request, stage="SANITIZED_INPUT", evidence=item, expires_at=LATER, nonce=str(uuid4())),
    )
    job.confirm_sanitized("sanitize", 4)
    job.normalize("normalize", 5)
    improvements = ()
    if job.request.material_request.route is UseRoute.ADAPTIVE_REIMPLEMENTATION:
        improvements = (ImprovementEvidence("SAFETY", "sha256:" + "4" * 64, "none", "validated"),)
    payload = originality_payload_fingerprint(
        candidate_content=candidate, route=job.request.material_request.route, evidence=improvements
    )
    att = es.sign(
        job.request.material_request, rights, stage="ORIGINALITY",
        stage_payload_fingerprint=payload, decision=ReviewDecision.APPROVE,
        expires_at=LATER, nonce=str(uuid4()),
    )
    job.approve_candidate(
        "candidate", 6, candidate, improvements, att,
        bs.sign(job.request, stage="ORIGINALITY", evidence=att, expires_at=LATER, nonce=str(uuid4())),
    )


@pytest.mark.parametrize("route", [UseRoute.LICENSED_REUSE, UseRoute.ADAPTIVE_REIMPLEMENTATION])
def test_happy_paths_stop_at_candidate(route):
    job, es, _, _, bs = setup(route)
    rights = advance_to_capture(job, es, bs)
    finish(job, es, bs, rights)
    assert job.state is JobState.ASSET_CANDIDATE
    assert job.candidate.status == "CANDIDATE_NOT_OWNED_ASSET"
    assert not hasattr(JobState, "OWNED_ASSET")
    job.verify_ledger()


def test_auth_without_user_action_accepts_only_opaque_grant():
    job, _, auth_signer, _, bs = setup(with_auth=True)
    job.start("start", 0)
    att = auth_signer.sign_preflight(
        request=job.request.auth_request, expires_at=LATER, nonce=str(uuid4()),
        official_domain=True, auth_method_allowlisted=True, scopes_minimal=True,
        source_authorized=True, robots_terms_license_ok=True,
        assetization_possible=True, privacy_secret_boundary_ok=True,
    )
    grant = OpaqueGrant(f"grantref:{uuid4()}", "https://example.com", ("read",), "authorized analysis", LATER)
    job.submit_auth_preflight(
        "auth", 1, att,
        bs.sign(job.request, stage="AUTH_PREFLIGHT", evidence=att, expires_at=LATER, nonce=str(uuid4())),
        grant=grant,
    )
    assert job.state is JobState.RIGHTS_REVIEW


def test_missing_grant_rolls_back_every_mutation_then_retries():
    job, _, auth_signer, _, bs = setup(with_auth=True)
    job.start("start", 0)
    att = auth_signer.sign_preflight(
        request=job.request.auth_request, expires_at=LATER, nonce=str(uuid4()),
        official_domain=True, auth_method_allowlisted=True, scopes_minimal=True,
        source_authorized=True, robots_terms_license_ok=True,
        assetization_possible=True, privacy_secret_boundary_ok=True,
    )
    binding = bs.sign(
        job.request, stage="AUTH_PREFLIGHT", evidence=att, expires_at=LATER, nonce=str(uuid4())
    )
    before = (job.state, job.version, tuple(job.events), set(job._used_nonces), job._auth.state)
    with pytest.raises(JobError, match="OPAQUE_GRANT_REQUIRED"):
        job.submit_auth_preflight("auth", 1, att, binding)
    assert (job.state, job.version, tuple(job.events), set(job._used_nonces), job._auth.state) == before
    assert not job._auth._used_nonces
    grant = OpaqueGrant(
        f"grantref:{uuid4()}", "https://example.com", ("read",), "authorized analysis", LATER
    )
    job.submit_auth_preflight("auth", 1, att, binding, grant=grant)
    assert job.state is JobState.RIGHTS_REVIEW


def test_valid_binding_with_invalid_inner_auth_signature_is_atomic():
    job, _, auth_signer, _, bs = setup(with_auth=True)
    job.start("start", 0)
    valid = auth_signer.sign_preflight(
        request=job.request.auth_request, expires_at=LATER, nonce=str(uuid4()),
        official_domain=True, auth_method_allowlisted=True, scopes_minimal=True,
        source_authorized=True, robots_terms_license_ok=True,
        assetization_possible=True, privacy_secret_boundary_ok=True,
    )
    invalid = replace(valid, signature="00" * 64)
    binding = bs.sign(
        job.request, stage="AUTH_PREFLIGHT", evidence=invalid, expires_at=LATER, nonce=str(uuid4())
    )
    before = (job.state, job.version, tuple(job.events), set(job._used_nonces))
    with pytest.raises(ValueError, match="INVALID_ATTESTATION_SIGNATURE"):
        job.submit_auth_preflight("auth", 1, invalid, binding)
    assert (job.state, job.version, tuple(job.events), set(job._used_nonces)) == before
    assert not job._auth._used_nonces

    grant = OpaqueGrant(
        f"grantref:{uuid4()}", "https://example.com", ("read",), "authorized analysis", LATER
    )
    corrected_binding = bs.sign(
        job.request, stage="AUTH_PREFLIGHT", evidence=valid, expires_at=LATER, nonce=str(uuid4())
    )
    job.submit_auth_preflight("auth", 1, valid, corrected_binding, grant=grant)
    assert job.state is JobState.RIGHTS_REVIEW


def test_auth_with_user_action_requires_mediator_attestation():
    job, _, auth_signer, mediator, bs = setup(with_auth=True, actions=("consent",))
    job.start("start", 0)
    preflight = auth_signer.sign_preflight(
        request=job.request.auth_request, expires_at=LATER, nonce=str(uuid4()),
        official_domain=True, auth_method_allowlisted=True, scopes_minimal=True,
        source_authorized=True, robots_terms_license_ok=True,
        assetization_possible=True, privacy_secret_boundary_ok=True,
    )
    job.submit_auth_preflight(
        "pre", 1, preflight,
        bs.sign(job.request, stage="AUTH_PREFLIGHT", evidence=preflight, expires_at=LATER, nonce=str(uuid4())),
    )
    assert job.state is JobState.USER_ACTION_REQUIRED
    grant = OpaqueGrant(f"grantref:{uuid4()}", "https://example.com", ("read",), "authorized analysis", LATER)
    action = mediator.sign_user_actions(
        request=job.request.auth_request, actions=("consent",), grant_reference=grant.reference,
        expires_at=LATER, nonce=str(uuid4()),
    )
    job.submit_user_grant(
        "grant", 2, grant, action,
        bs.sign(job.request, stage="USER_ACTION", evidence=action, expires_at=LATER, nonce=str(uuid4())),
    )
    assert job.state is JobState.RIGHTS_REVIEW


def test_cross_job_tenant_and_request_binding_substitution_blocked():
    job, es, _, _, _bs = setup()
    other, _, _, _, other_bs = setup()
    job.start("start", 0)
    rights = evidence()
    att = es.sign(
        job.request.material_request, rights, stage="RIGHTS",
        stage_payload_fingerprint=rights.fingerprint, decision=ReviewDecision.APPROVE,
        expires_at=LATER, nonce=str(uuid4()),
    )
    wrong = other_bs.sign(other.request, stage="RIGHTS", evidence=att, expires_at=LATER, nonce=str(uuid4()))
    with pytest.raises(JobError, match="EVIDENCE_BINDING_MISMATCH"):
        job.review_rights("rights", 1, rights, att, wrong)
    assert job.version == 1


def test_idempotent_retry_conflict_and_stale_version():
    job, *_ = setup()
    first = job.start("same", 0)
    assert job.start("same", 999) == first
    with pytest.raises(JobError, match="IDEMPOTENCY_CONFLICT"):
        job._command("same", 1, {"different": True}, lambda: None, "NOPE")
    with pytest.raises(JobError, match="STALE_VERSION"):
        job.cancel("cancel", 0)


@pytest.mark.parametrize("mutation", ["tamper", "truncate", "reorder"])
def test_ledger_tamper_truncate_and_reorder_detected(mutation):
    job, *_ = setup()
    job.start("start", 0)
    job.cancel("cancel", 1)
    if mutation == "tamper":
        job.events[1] = replace(job.events[1], event_type="ALTERED")
    elif mutation == "truncate":
        job.events.pop()
    else:
        job.events[0], job.events[1] = job.events[1], job.events[0]
    with pytest.raises(JobError, match="LEDGER_INTEGRITY_FAILURE"):
        job.verify_ledger()


def test_expiry_recovery_and_cancel_are_terminal():
    clock = [NOW]
    job, *_ = setup()
    job._now_provider = lambda: clock[0]
    job.start("start", 0)
    clock[0] = LATER
    with pytest.raises(JobError, match="JOB_EXPIRED"):
        job.recover()
    assert job.state is JobState.EXPIRED
    other, *_ = setup()
    other.start("start", 0)
    other.cancel("cancel", 1)
    with pytest.raises(JobError, match="TERMINAL_STATE"):
        other.recover()


def test_recovery_revalidates_evidence_expiry():
    clock = [NOW]
    job, es, _, _, bs = setup()
    job._now_provider = lambda: clock[0]
    job.start("start", 0)
    rights = evidence()
    att = es.sign(
        job.request.material_request, rights, stage="RIGHTS",
        stage_payload_fingerprint=rights.fingerprint, decision=ReviewDecision.APPROVE,
        expires_at=NOW + timedelta(minutes=10), nonce=str(uuid4()),
    )
    binding = bs.sign(
        job.request, stage="RIGHTS", evidence=att,
        expires_at=NOW + timedelta(minutes=10), nonce=str(uuid4()),
    )
    job.review_rights("rights", 1, rights, att, binding)
    clock[0] = NOW + timedelta(minutes=11)
    with pytest.raises(JobError, match="EVIDENCE_EXPIRED"):
        job.recover()
    assert job.state is JobState.EXPIRED


def test_raw_secret_rejected_from_identity_and_sanitized_envelope():
    correlation = uuid4()
    with pytest.raises(JobError, match="RAW_SECRET_BLOCKED"):
        AcquisitionJobRequest(
            "tenant", "password=supersecret", "key", correlation, material(correlation)
        )
    job, es, _, _, bs = setup()
    advance_to_capture(job, es, bs)
    bad = replace(envelope(), capture=replace(envelope().capture, body="token=supersecret"))
    binding = bs.sign(
        job.request, stage="SANITIZED_INPUT", evidence=bad, expires_at=LATER, nonce=str(uuid4())
    )
    with pytest.raises(ValueError, match="UNSANITIZED_CAPTURE_BLOCKED"):
        job.accept_sanitized_input("bad", 3, bad, binding)
    assert job.state is JobState.QUARANTINED


def test_opaque_uuid_with_phone_shaped_digits_is_valid_identity():
    correlation = uuid4()
    opaque = "00000000-0000-4000-8000-a01012345678"
    request = AcquisitionJobRequest(
        opaque, opaque, opaque, correlation, material(correlation)
    )
    assert request.tenant_id == opaque
    with pytest.raises(JobError, match="RAW_SECRET_BLOCKED"):
        AcquisitionJobRequest(
            opaque, opaque, "password=supersecret", correlation, material(correlation)
        )


def test_invalid_inner_originality_signature_rolls_back_then_corrects():
    job, es, _, _, bs = setup()
    rights = advance_to_capture(job, es, bs)
    item = envelope()
    job.accept_sanitized_input(
        "capture", 3, item,
        bs.sign(job.request, stage="SANITIZED_INPUT", evidence=item, expires_at=LATER, nonce=str(uuid4())),
    )
    job.confirm_sanitized("sanitize", 4)
    job.normalize("normalize", 5)
    candidate = "function improved(x,y){return Number(x)+Number(y)}"
    payload = originality_payload_fingerprint(
        candidate_content=candidate, route=UseRoute.LICENSED_REUSE, evidence=()
    )
    valid = es.sign(
        job.request.material_request, rights, stage="ORIGINALITY",
        stage_payload_fingerprint=payload, decision=ReviewDecision.APPROVE,
        expires_at=LATER, nonce=str(uuid4()),
    )
    invalid = replace(valid, signature="00" * 64)
    binding = bs.sign(
        job.request, stage="ORIGINALITY", evidence=invalid, expires_at=LATER, nonce=str(uuid4())
    )
    before = (
        job.state, job.version, tuple(job.events), set(job._used_nonces),
        job._material.state, set(job._material._nonces), job.candidate,
    )
    with pytest.raises(ValueError, match="INVALID_ATTESTATION_SIGNATURE"):
        job.approve_candidate("candidate", 6, candidate, (), invalid, binding)
    assert (
        job.state, job.version, tuple(job.events), set(job._used_nonces),
        job._material.state, set(job._material._nonces), job.candidate,
    ) == before
    corrected_binding = bs.sign(
        job.request, stage="ORIGINALITY", evidence=valid, expires_at=LATER, nonce=str(uuid4())
    )
    job.approve_candidate("candidate", 6, candidate, (), valid, corrected_binding)
    assert job.state is JobState.ASSET_CANDIDATE


def test_candidate_secret_leak_commits_one_terminal_quarantine_event():
    job, es, _, _, bs = setup()
    rights = advance_to_capture(job, es, bs)
    item = envelope()
    job.accept_sanitized_input(
        "capture", 3, item,
        bs.sign(job.request, stage="SANITIZED_INPUT", evidence=item, expires_at=LATER, nonce=str(uuid4())),
    )
    job.confirm_sanitized("sanitize", 4)
    job.normalize("normalize", 5)
    candidate = "const token=supersecret"
    payload = originality_payload_fingerprint(
        candidate_content=candidate, route=UseRoute.LICENSED_REUSE, evidence=()
    )
    att = es.sign(
        job.request.material_request, rights, stage="ORIGINALITY",
        stage_payload_fingerprint=payload, decision=ReviewDecision.APPROVE,
        expires_at=LATER, nonce=str(uuid4()),
    )
    binding = bs.sign(
        job.request, stage="ORIGINALITY", evidence=att, expires_at=LATER, nonce=str(uuid4())
    )
    before_events = len(job.events)
    with pytest.raises(ValueError, match="CANDIDATE_SECRET_OR_PII_BLOCKED"):
        job.approve_candidate("candidate", 6, candidate, (), att, binding)
    assert job.state is JobState.QUARANTINED
    assert len(job.events) == before_events + 1
    assert job.events[-1].event_type == "COMMAND_REJECTED"


def test_originality_review_commits_one_review_event_and_consumes_evidence():
    job, es, _, _, bs = setup()
    rights = advance_to_capture(job, es, bs)
    item = envelope()
    job.accept_sanitized_input(
        "capture", 3, item,
        bs.sign(job.request, stage="SANITIZED_INPUT", evidence=item, expires_at=LATER, nonce=str(uuid4())),
    )
    job.confirm_sanitized("sanitize", 4)
    job.normalize("normalize", 5)
    candidate = "function improved(x,y){return Number(x)+Number(y)}"
    payload = originality_payload_fingerprint(
        candidate_content=candidate, route=UseRoute.LICENSED_REUSE, evidence=()
    )
    att = es.sign(
        job.request.material_request, rights, stage="ORIGINALITY",
        stage_payload_fingerprint=payload, decision=ReviewDecision.REVIEW,
        expires_at=LATER, nonce=str(uuid4()),
    )
    binding = bs.sign(
        job.request, stage="ORIGINALITY", evidence=att, expires_at=LATER, nonce=str(uuid4())
    )
    before_events = len(job.events)
    with pytest.raises(ValueError, match="ORIGINALITY_NOT_APPROVED"):
        job.approve_candidate("review", 6, candidate, (), att, binding)
    assert job.state is JobState.ETHERNIAN_REVIEW
    assert job._material.state.value == "ETHERNIAN_REVIEW"
    assert job.version == 7
    assert len(job.events) == before_events + 1
    assert job.events[-1].event_type == "COMMAND_REVIEW_REQUIRED"
    assert binding.nonce in job._used_nonces
    assert ("ORIGINALITY", att.nonce) in job._material._nonces
    job.verify_ledger()

    stable = (job.version, tuple(job.events), set(job._used_nonces), set(job._material._nonces))
    with pytest.raises(JobError, match="INVALID_STATE_TRANSITION"):
        job.approve_candidate("review", 7, candidate, (), att, binding)
    assert (job.version, tuple(job.events), set(job._used_nonces), set(job._material._nonces)) == stable


def test_forbidden_state_skip_fails_closed():
    job, *_ = setup()
    with pytest.raises(JobError, match="INVALID_STATE_TRANSITION"):
        job.normalize("skip", 0)
