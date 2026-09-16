from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .acquisition_orchestrator import (
    AcquisitionJob,
    AcquisitionJobRequest,
    JobBindingSigner,
    JobError,
    JobState,
    SanitizedInputEnvelope,
)
from .authorized_material import (
    CollectionPosture,
    EthernianSigner,
    ImprovementEvidence,
    LicenseTerms,
    MaterialError,
    MaterialRequest,
    ReviewDecision,
    RightsEvidence,
    SanitizedCapture,
    SourceRights,
    UseRoute,
    originality_payload_fingerprint,
)
from .durable_review import DurableReviewRepository, ReviewStage
from .mediated_auth import AttestationSigner, AuthMethod, AuthRequest, OpaqueGrant
from .release_certification import VectorResult, digest

NOW = datetime(2030, 1, 1, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def _key(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _uuid(number: int) -> str:
    return f"00000000-0000-0000-0000-{number:012d}"


class CanonicalVectorSuite:
    """Sealed deterministic #032–#035 execution suite used by the release gate."""

    __slots__ = ()

    def execute(self) -> tuple[VectorResult, ...]:
        return tuple(sorted((
            self._candidate("NO_AUTH_REUSE", UseRoute.LICENSED_REUSE, authenticated=False),
            self._candidate("AUTH_ADAPTIVE", UseRoute.ADAPTIVE_REIMPLEMENTATION, authenticated=True),
            self._review_required(), self._denied(), self._expiry_recovery(),
        ), key=lambda item: item.vector_id))

    @staticmethod
    def _context(vector_id: str, route: UseRoute, *, authenticated: bool, clock):
        index = {"NO_AUTH_REUSE": 1, "AUTH_ADAPTIVE": 2, "REVIEW_REQUIRED": 3,
                 "DENY": 4, "EXPIRY_RECOVERY": 5}[vector_id]
        correlation = UUID(_uuid(100 + index))
        material = MaterialRequest(
            "https://example.com/app.js", ("https://example.com",), route,
            "authorized analysis", ("application/javascript",), 2, 10_000, LATER,
            correlation_id=str(correlation),
        )
        auth = None
        if authenticated:
            auth = AuthRequest(
                "https://example.com", "authorized analysis", ("read",), True,
                ("javascript",), "authorized workspace", "owner permission", ("privacy",),
                LATER, correlation, AuthMethod.BROWSER_AUTH, ("consent",),
            )
        request = AcquisitionJobRequest(
            "tenant-cert", f"principal-{index}", f"vector-{index}", correlation, material, auth,
            UUID(_uuid(200 + index)),
        )
        ethernian, mediator, binder = _key(10), _key(11), _key(12)
        job = AcquisitionJob(
            request, ethernian_public_key=ethernian.public_key(),
            mediator_public_key=mediator.public_key(), binding_public_key=binder.public_key(),
            now_provider=clock,
        )
        return job, EthernianSigner(ethernian), AttestationSigner(ethernian), \
            AttestationSigner(mediator), JobBindingSigner(binder), ethernian

    @staticmethod
    def _rights() -> RightsEvidence:
        return RightsEvidence(
            SourceRights.ATTRIBUTION_LICENSE, "sha256:" + "1" * 64,
            LicenseTerms("MIT", True, True, True, attribution_required=True), "example owner",
        )

    @staticmethod
    def _persist(job: AcquisitionJob, key: Ed25519PrivateKey, candidate: bool = False):
        with TemporaryDirectory() as directory:
            repo = DurableReviewRepository(
                Path(directory) / "cert.sqlite", ethernian_public_key=key.public_key(),
                now_provider=job._now_provider,
            )
            initial = AcquisitionJob(
                job.request, ethernian_public_key=key.public_key(),
                mediator_public_key=key.public_key(), binding_public_key=key.public_key(),
                now_provider=lambda: job.events[0].timestamp,
            )
            repo.create_job(initial)
            repo.save_job(job, expected_version=0)
            if candidate:
                assert job.candidate is not None
                repo.put_candidate_manifest(
                    job.request.tenant_id, str(job.request.job_id),
                    candidate_hash=job.candidate.content_hash,
                    quarantine_reference=f"quarantine:{_uuid(901)}",
                    license_obligations=job.candidate.obligations,
                )
                manifest = repo.get_candidate_manifest(job.request.tenant_id, str(job.request.job_id))
                assert manifest and manifest["candidate_hash"] == job.candidate.content_hash
            record = repo.load_job(job.request.tenant_id, str(job.request.job_id))
        return record

    @staticmethod
    def _result(vector_id: str, job: AcquisitionJob, trace: tuple[str, ...]) -> VectorResult:
        job.verify_ledger()
        actual = tuple(event.event_type for event in job.events)
        if actual != trace:
            raise JobError("CERTIFICATION_TRACE_MISMATCH")
        candidate = job.candidate
        return VectorResult(
            vector_id, True, job.state.value, job.request.job_fingerprint,
            job.events[-1].event_hash, candidate.content_hash if candidate else None,
            candidate.status if candidate else None,
            candidate.obligations if candidate else (),
            (digest({"events": actual}), digest({"versions": tuple(e.version for e in job.events)})),
            digest({"trace": trace}),
        )

    def _candidate(self, vector_id: str, route: UseRoute, *, authenticated: bool) -> VectorResult:
        clock = lambda: NOW
        job, material_signer, auth_signer, mediator, binder, key = self._context(
            vector_id, route, authenticated=authenticated, clock=clock
        )
        job.start("start", 0)
        version = 1
        if authenticated:
            assert job.request.auth_request is not None
            preflight = auth_signer.sign_preflight(
                request=job.request.auth_request, expires_at=LATER, nonce=_uuid(301),
                official_domain=True, auth_method_allowlisted=True, scopes_minimal=True,
                source_authorized=True, robots_terms_license_ok=True,
                assetization_possible=True, privacy_secret_boundary_ok=True,
            )
            job.submit_auth_preflight(
                "preflight", version, preflight,
                binder.sign(job.request, stage="AUTH_PREFLIGHT", evidence=preflight,
                            expires_at=LATER, nonce=_uuid(302)),
            )
            version += 1
            grant = OpaqueGrant(
                f"grantref:{_uuid(303)}", "https://example.com", ("read",),
                "authorized analysis", LATER,
            )
            action = mediator.sign_user_actions(
                request=job.request.auth_request, actions=("consent",),
                grant_reference=grant.reference, expires_at=LATER, nonce=_uuid(304),
            )
            job.submit_user_grant(
                "grant", version, grant, action,
                binder.sign(job.request, stage="USER_ACTION", evidence=action,
                            expires_at=LATER, nonce=_uuid(305)),
            )
            version += 1
        rights = self._rights()
        rights_att = material_signer.sign(
            job.request.material_request, rights, stage="RIGHTS",
            stage_payload_fingerprint=rights.fingerprint, decision=ReviewDecision.APPROVE,
            expires_at=LATER, nonce=_uuid(401),
        )
        job.review_rights(
            "rights", version, rights, rights_att,
            binder.sign(job.request, stage="RIGHTS", evidence=rights_att,
                        expires_at=LATER, nonce=_uuid(402)),
        )
        version += 1
        posture = CollectionPosture("ALLOW", "OK")
        collection_att = material_signer.sign(
            job.request.material_request, rights, stage="COLLECTION_POLICY",
            stage_payload_fingerprint=posture.fingerprint, decision=ReviewDecision.APPROVE,
            expires_at=LATER, nonce=_uuid(403),
        )
        job.review_collection(
            "collection", version, posture, collection_att,
            binder.sign(job.request, stage="COLLECTION", evidence=collection_att,
                        expires_at=LATER, nonce=_uuid(404)),
        )
        version += 1
        capture = SanitizedCapture(
            "https://example.com/app.js", "application/javascript",
            "function sourceAdd(a,b){return a+b}", None, None, None, "sha256:" + "2" * 64,
        )
        envelope = SanitizedInputEnvelope(capture, f"quarantine:{_uuid(405)}", "sha256:" + "3" * 64)
        job.accept_sanitized_input(
            "capture", version, envelope,
            binder.sign(job.request, stage="SANITIZED_INPUT", evidence=envelope,
                        expires_at=LATER, nonce=_uuid(406)),
        )
        version += 1
        job.confirm_sanitized("sanitize", version)
        version += 1
        job.normalize("normalize", version)
        version += 1
        candidate_text = "const robustTotal=(values)=>values.reduce((total,item)=>total+Number(item),0);"
        improvements = () if route is UseRoute.LICENSED_REUSE else (
            ImprovementEvidence("SAFETY", "sha256:" + "4" * 64, "unchecked", "validated"),
        )
        payload = originality_payload_fingerprint(
            candidate_content=candidate_text, route=route, evidence=improvements
        )
        original_att = material_signer.sign(
            job.request.material_request, rights, stage="ORIGINALITY",
            stage_payload_fingerprint=payload, decision=ReviewDecision.APPROVE,
            expires_at=LATER, nonce=_uuid(407),
        )
        job.approve_candidate(
            "candidate", version, candidate_text, improvements, original_att,
            binder.sign(job.request, stage="ORIGINALITY", evidence=original_att,
                        expires_at=LATER, nonce=_uuid(408)),
        )
        self._persist(job, key, candidate=True)
        expected = ["JOB_CREATED", "JOB_STARTED"]
        if authenticated:
            expected += ["AUTH_PREFLIGHT_VERIFIED", "USER_GRANT_VERIFIED"]
        expected += ["RIGHTS_REVIEWED", "COLLECTION_REVIEWED", "SANITIZED_INPUT_ACCEPTED",
                     "SANITIZATION_CONFIRMED", "MATERIAL_NORMALIZED", "ASSET_CANDIDATE_CREATED"]
        return self._result(vector_id, job, tuple(expected))

    def _review_required(self) -> VectorResult:
        job, signer, _, _, binder, key = self._context(
            "REVIEW_REQUIRED", UseRoute.LICENSED_REUSE, authenticated=False, clock=lambda: NOW
        )
        job.start("start", 0)
        rights = self._rights()
        att = signer.sign(
            job.request.material_request, rights, stage="RIGHTS",
            stage_payload_fingerprint=rights.fingerprint, decision=ReviewDecision.REVIEW,
            expires_at=LATER, nonce=_uuid(501),
        )
        job.review_rights("rights", 1, rights, att, binder.sign(
            job.request, stage="RIGHTS", evidence=att, expires_at=LATER, nonce=_uuid(502)
        ))
        with TemporaryDirectory() as directory:
            repo = DurableReviewRepository(Path(directory) / "cert.sqlite",
                                           ethernian_public_key=key.public_key(),
                                           now_provider=lambda: NOW)
            initial = AcquisitionJob(
                job.request, ethernian_public_key=key.public_key(),
                mediator_public_key=key.public_key(), binding_public_key=key.public_key(),
                now_provider=lambda: NOW,
            )
            record = repo.create_job(initial)
            record = repo.save_job(job, expected_version=0)
            task = repo.create_review(
                record.tenant_id, record.job_id, stage=ReviewStage.RIGHTS,
                reason_code="RIGHTS_CHECK", evidence_fingerprint=rights.fingerprint,
                expires_at=LATER,
            )
            assert repo.list_open_reviews(record.tenant_id, record.job_id) == (task,)
            repo.load_job(record.tenant_id, record.job_id)
        return self._result("REVIEW_REQUIRED", job,
                            ("JOB_CREATED", "JOB_STARTED", "RIGHTS_REVIEWED"))

    def _denied(self) -> VectorResult:
        job, signer, _, _, binder, key = self._context(
            "DENY", UseRoute.LICENSED_REUSE, authenticated=False, clock=lambda: NOW
        )
        job.start("start", 0)
        rights = self._rights()
        att = signer.sign(
            job.request.material_request, rights, stage="RIGHTS",
            stage_payload_fingerprint=rights.fingerprint, decision=ReviewDecision.DENY,
            expires_at=LATER, nonce=_uuid(601),
        )
        try:
            job.review_rights("rights", 1, rights, att, binder.sign(
                job.request, stage="RIGHTS", evidence=att, expires_at=LATER, nonce=_uuid(602)
            ))
        except (JobError, MaterialError) as error:
            assert error.code == "RIGHTS_DENIED"
        assert job.state is JobState.DENIED
        self._persist(job, key)
        return self._result("DENY", job, ("JOB_CREATED", "JOB_STARTED", "COMMAND_REJECTED"))

    def _expiry_recovery(self) -> VectorResult:
        clock = [NOW]
        job, _, _, _, _, key = self._context(
            "EXPIRY_RECOVERY", UseRoute.LICENSED_REUSE, authenticated=False, clock=lambda: clock[0]
        )
        job.start("start", 0)
        clock[0] = LATER
        try:
            job.recover()
        except JobError as error:
            assert error.code == "JOB_EXPIRED"
        assert job.state is JobState.EXPIRED
        self._persist(job, key)
        return self._result("EXPIRY_RECOVERY", job,
                            ("JOB_CREATED", "JOB_STARTED", "JOB_EXPIRED"))
