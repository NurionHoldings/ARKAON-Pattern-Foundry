from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .authorized_material import (
    AssetCandidate,
    AuthorizedMaterialPipeline,
    CollectionPosture,
    EthernianAttestation,
    ImprovementEvidence,
    MaterialError,
    MaterialRequest,
    MaterialState,
    RightsEvidence,
    SanitizedCapture,
)
from .learning_safety import scan_learning_text
from .mediated_auth import (
    AuthGateError,
    AuthRequest,
    AuthState,
    MediatedAuthAcquisition,
    OpaqueGrant,
    PreflightAttestation,
    UserActionAttestation,
)


class JobError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class JobState(StrEnum):
    QUEUED = "QUEUED"
    AUTH_PREFLIGHT_REQUIRED = "AUTH_PREFLIGHT_REQUIRED"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    RIGHTS_REVIEW = "RIGHTS_REVIEW"
    COLLECTION_REVIEW = "COLLECTION_REVIEW"
    READY_TO_CAPTURE = "READY_TO_CAPTURE"
    SANITIZE = "SANITIZE"
    NORMALIZE = "NORMALIZE"
    ORIGINALITY_REVIEW = "ORIGINALITY_REVIEW"
    ASSET_CANDIDATE = "ASSET_CANDIDATE"
    ETHERNIAN_REVIEW = "ETHERNIAN_REVIEW"
    DENIED = "DENIED"
    QUARANTINED = "QUARANTINED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


TERMINAL = frozenset(
    {JobState.ASSET_CANDIDATE, JobState.DENIED, JobState.QUARANTINED,
     JobState.EXPIRED, JobState.CANCELLED, JobState.FAILED}
)
_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"\Aquarantine:[0-9a-f-]{36}\Z")
_NONCE = re.compile(r"\A[0-9a-f-]{36}\Z")


def _time(value: datetime) -> str:
    if value.tzinfo is None:
        raise JobError("NAIVE_TIMESTAMP")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _json(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()


def _hash(data: object) -> str:
    return "sha256:" + sha256(_json(data)).hexdigest()


def _evidence_fingerprint(item: object) -> str:
    data = asdict(item) if is_dataclass(item) else item
    if isinstance(data, dict):
        data = dict(data)
        data.pop("signature", None)
    return _hash(data)


@dataclass(frozen=True)
class AcquisitionJobRequest:
    tenant_id: str
    principal_id: str
    idempotency_key: str
    correlation_id: UUID
    material_request: MaterialRequest
    auth_request: AuthRequest | None = None
    job_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not all((self.tenant_id.strip(), self.principal_id.strip(), self.idempotency_key.strip())):
            raise JobError("MISSING_JOB_BINDING")
        if scan_learning_text(f"{self.tenant_id} {self.principal_id} {self.idempotency_key}"):
            raise JobError("RAW_SECRET_BLOCKED")
        if self.auth_request and self.auth_request.correlation_id != self.correlation_id:
            raise JobError("CORRELATION_MISMATCH")
        if self.material_request.correlation_id != str(self.correlation_id):
            raise JobError("CORRELATION_MISMATCH")

    @property
    def request_fingerprint(self) -> str:
        return _hash({
            "auth_request": self.auth_request.fingerprint if self.auth_request else None,
            "correlation_id": str(self.correlation_id),
            "idempotency_key": self.idempotency_key,
            "material_request": self.material_request.fingerprint,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
        })

    @property
    def job_fingerprint(self) -> str:
        return _hash({"job_id": str(self.job_id), "request_fingerprint": self.request_fingerprint})


@dataclass(frozen=True)
class JobEvidenceBinding:
    job_fingerprint: str
    request_fingerprint: str
    tenant_id: str
    principal_id: str
    stage: str
    evidence_fingerprint: str
    expires_at: datetime
    nonce: str
    signature: str


class JobBindingSigner:
    """External reviewer helper; the orchestrator is given only the public key."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key

    def sign(
        self, request: AcquisitionJobRequest, *, stage: str,
        evidence: object, expires_at: datetime, nonce: str,
    ) -> JobEvidenceBinding:
        unsigned = JobEvidenceBinding(
            request.job_fingerprint, request.request_fingerprint, request.tenant_id,
            request.principal_id, stage, _evidence_fingerprint(evidence), expires_at, nonce, "",
        )
        return JobEvidenceBinding(
            **{**asdict(unsigned), "signature": self._key.sign(_json(asdict(unsigned))).hex()}
        )


@dataclass(frozen=True)
class SanitizedInputEnvelope:
    capture: SanitizedCapture
    quarantine_reference: str
    raw_content_hash: str

    def __post_init__(self) -> None:
        if not _REF.fullmatch(self.quarantine_reference) or not _DIGEST.fullmatch(
            self.raw_content_hash
        ):
            raise JobError("INVALID_QUARANTINE_REFERENCE")


@dataclass(frozen=True)
class JobEvent:
    sequence: int
    job_fingerprint: str
    event_type: str
    state: JobState
    version: int
    timestamp: datetime
    metadata: Mapping[str, str]
    previous_hash: str
    event_hash: str


@dataclass(frozen=True)
class CommandReceipt:
    command_id: str
    payload_fingerprint: str
    resulting_state: JobState
    resulting_version: int
    event_hash: str


class AcquisitionJob:
    """Fail-closed coordinator. It performs no network or credential handling."""

    def __init__(
        self, request: AcquisitionJobRequest, *, ethernian_public_key: Ed25519PublicKey,
        mediator_public_key: Ed25519PublicKey, binding_public_key: Ed25519PublicKey,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.request = request
        self.state = JobState.QUEUED
        self.version = 0
        self.events: list[JobEvent] = []
        self.candidate: AssetCandidate | None = None
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._binding_key = binding_public_key
        self._used_nonces: set[str] = set()
        self._verified_evidence_expiries: list[datetime] = []
        self._receipts: dict[str, CommandReceipt] = {}
        self._material = AuthorizedMaterialPipeline(
            request.material_request, ethernian_public_key=ethernian_public_key,
            now_provider=self._now_provider,
        )
        self._auth = (
            MediatedAuthAcquisition(
                request.auth_request, ethernian_public_key=ethernian_public_key,
                mediator_public_key=mediator_public_key, now_provider=self._now_provider,
            )
            if request.auth_request else None
        )
        self._append("JOB_CREATED", {})

    def _now(self) -> datetime:
        value = self._now_provider()
        if value.tzinfo is None:
            raise JobError("NAIVE_CLOCK")
        return value

    def _check_live(self) -> None:
        if self.state in TERMINAL:
            raise JobError("TERMINAL_STATE")
        expiry = min(
            self.request.material_request.expires_at,
            self.request.auth_request.expires_at if self.request.auth_request else datetime.max.replace(tzinfo=UTC),
        )
        if self._now() >= expiry:
            self.state = JobState.EXPIRED
            self.version += 1
            self._append("JOB_EXPIRED", {})
            raise JobError("JOB_EXPIRED")

    def _append(self, kind: str, metadata: Mapping[str, str]) -> None:
        # Metadata is deliberately limited to non-secret references and digests.
        if not re.fullmatch(r"[A-Z][A-Z_]+", kind) or set(metadata) - {
            "payload_fingerprint",
            "reason_code",
        }:
            raise JobError("RAW_SECRET_BLOCKED")
        if "payload_fingerprint" in metadata and not _DIGEST.fullmatch(
            metadata["payload_fingerprint"]
        ):
            raise JobError("RAW_SECRET_BLOCKED")
        if "reason_code" in metadata and not re.fullmatch(
            r"[A-Z][A-Z0-9_]+", metadata["reason_code"]
        ):
            raise JobError("RAW_SECRET_BLOCKED")
        previous = self.events[-1].event_hash if self.events else "GENESIS"
        sequence = len(self.events) + 1
        timestamp = self._now()
        body = {
            "event_type": kind, "job_fingerprint": self.request.job_fingerprint,
            "metadata": dict(metadata), "previous_hash": previous, "sequence": sequence,
            "state": self.state.value, "timestamp": _time(timestamp), "version": self.version,
        }
        self.events.append(JobEvent(
            sequence, self.request.job_fingerprint, kind, self.state, self.version,
            timestamp, dict(metadata), previous, _hash(body),
        ))

    def verify_ledger(self) -> None:
        if (
            not self.events
            or self.events[0].event_type != "JOB_CREATED"
            or len(self.events) != self.version + 1
            or self.events[-1].version != self.version
            or self.events[-1].state is not self.state
        ):
            raise JobError("LEDGER_INTEGRITY_FAILURE")
        previous = "GENESIS"
        for expected, event in enumerate(self.events, 1):
            body = {
                "event_type": event.event_type, "job_fingerprint": event.job_fingerprint,
                "metadata": dict(event.metadata), "previous_hash": event.previous_hash,
                "sequence": event.sequence, "state": event.state.value,
                "timestamp": _time(event.timestamp), "version": event.version,
            }
            if (event.sequence != expected or event.previous_hash != previous
                    or event.job_fingerprint != self.request.job_fingerprint
                    or event.event_hash != _hash(body)):
                raise JobError("LEDGER_INTEGRITY_FAILURE")
            previous = event.event_hash

    def _verify_binding(self, item: JobEvidenceBinding, stage: str, evidence: object) -> None:
        expected = (
            self.request.job_fingerprint, self.request.request_fingerprint,
            self.request.tenant_id, self.request.principal_id, stage,
            _evidence_fingerprint(evidence),
        )
        actual = (
            item.job_fingerprint, item.request_fingerprint, item.tenant_id,
            item.principal_id, item.stage, item.evidence_fingerprint,
        )
        if actual != expected or not _NONCE.fullmatch(item.nonce):
            raise JobError("EVIDENCE_BINDING_MISMATCH")
        if item.expires_at.tzinfo is None or self._now() >= item.expires_at:
            raise JobError("EVIDENCE_EXPIRED")
        job_expiry = min(
            self.request.material_request.expires_at,
            self.request.auth_request.expires_at
            if self.request.auth_request
            else datetime.max.replace(tzinfo=UTC),
        )
        if item.expires_at > job_expiry:
            raise JobError("EVIDENCE_EXPIRY_OUT_OF_BOUNDS")
        if item.nonce in self._used_nonces:
            raise JobError("EVIDENCE_REPLAY_BLOCKED")
        unsigned = {**asdict(item), "signature": ""}
        try:
            self._binding_key.verify(bytes.fromhex(item.signature), _json(unsigned))
        except (InvalidSignature, ValueError, TypeError):
            raise JobError("INVALID_EVIDENCE_SIGNATURE") from None
        self._used_nonces.add(item.nonce)
        inner_expiry = getattr(evidence, "expires_at", item.expires_at)
        if not isinstance(inner_expiry, datetime) or inner_expiry.tzinfo is None:
            raise JobError("EVIDENCE_EXPIRED")
        self._verified_evidence_expiries.append(min(item.expires_at, inner_expiry))

    def _command(
        self, command_id: str, expected_version: int, payload: object,
        operation: Callable[[], None], event_type: str,
    ) -> CommandReceipt:
        payload_fp = _evidence_fingerprint(payload)
        prior = self._receipts.get(command_id)
        if prior:
            if prior.payload_fingerprint != payload_fp:
                raise JobError("IDEMPOTENCY_CONFLICT")
            return prior
        self.verify_ledger()
        if expected_version != self.version:
            raise JobError("STALE_VERSION")
        snapshot = self._snapshot()
        try:
            self._check_live()
            operation()
        except (JobError, MaterialError, AuthGateError) as error:
            mapped = self._failure_state(snapshot)
            policy_state = {
                "job_nonces": set(self._used_nonces),
                "evidence_expiries": list(self._verified_evidence_expiries),
                "material_state": self._material.state,
                "material_nonces": set(self._material._nonces),
                "auth_state": self._auth.state if self._auth is not None else None,
                "auth_nonces": set(self._auth._used_nonces) if self._auth is not None else set(),
            }
            self._restore(snapshot)
            if mapped in {
                JobState.ETHERNIAN_REVIEW,
                JobState.DENIED,
                JobState.QUARANTINED,
                JobState.EXPIRED,
                JobState.CANCELLED,
            }:
                self._commit_policy_state(mapped, policy_state)
                self.state = mapped
                self.version += 1
                event = (
                    "COMMAND_REVIEW_REQUIRED"
                    if mapped is JobState.ETHERNIAN_REVIEW
                    else "COMMAND_REJECTED"
                )
                self._append(event, {"reason_code": error.code})
            raise
        self.version += 1
        self._append(event_type, {"payload_fingerprint": payload_fp})
        receipt = CommandReceipt(
            command_id, payload_fp, self.state, self.version, self.events[-1].event_hash
        )
        self._receipts[command_id] = receipt
        return receipt

    def _commit_policy_state(self, mapped: JobState, policy: Mapping[str, object]) -> None:
        self._used_nonces = policy["job_nonces"]  # type: ignore[assignment]
        self._verified_evidence_expiries = policy["evidence_expiries"]  # type: ignore[assignment]
        material_state = policy["material_state"]
        material_map = {
            MaterialState.ETHERNIAN_REVIEW: JobState.ETHERNIAN_REVIEW,
            MaterialState.DENIED: JobState.DENIED,
            MaterialState.QUARANTINED: JobState.QUARANTINED,
            MaterialState.EXPIRED: JobState.EXPIRED,
        }
        if material_map.get(material_state) is mapped:
            self._material.state = material_state  # type: ignore[assignment]
            self._material._nonces = policy["material_nonces"]  # type: ignore[assignment]
        auth_state = policy["auth_state"]
        auth_map = {
            AuthState.DENIED: JobState.DENIED,
            AuthState.EXPIRED: JobState.EXPIRED,
            AuthState.REVOKED: JobState.CANCELLED,
        }
        if self._auth is not None and auth_map.get(auth_state) is mapped:
            self._auth.state = auth_state  # type: ignore[assignment]
            self._auth._used_nonces = policy["auth_nonces"]  # type: ignore[assignment]

    def _snapshot(self) -> dict[str, object]:
        auth = None
        if self._auth is not None:
            auth = {
                "state": self._auth.state,
                "grant": self._auth.grant,
                "receipt": self._auth.receipt,
                "audit_codes": list(self._auth.audit_codes),
                "used": self._auth._used,
                "used_nonces": set(self._auth._used_nonces),
            }
        material = {
            "state": self._material.state,
            "rights": self._material.rights,
            "sanitized": self._material.sanitized,
            "normalized": self._material.normalized,
            "capture": self._material._capture,
            "nonces": set(self._material._nonces),
            "requests": self._material._requests,
            "bytes": self._material._bytes,
            "source_identifiers": set(self._material._source_identifiers),
            "audit": list(self._material.audit),
        }
        return {
            "state": self.state,
            "version": self.version,
            "events": list(self.events),
            "candidate": self.candidate,
            "used_nonces": set(self._used_nonces),
            "evidence_expiries": list(self._verified_evidence_expiries),
            "receipts": dict(self._receipts),
            "auth": auth,
            "material": material,
        }

    def _restore(self, snapshot: Mapping[str, object]) -> None:
        self.state = snapshot["state"]  # type: ignore[assignment]
        self.version = snapshot["version"]  # type: ignore[assignment]
        self.events = snapshot["events"]  # type: ignore[assignment]
        self.candidate = snapshot["candidate"]  # type: ignore[assignment]
        self._used_nonces = snapshot["used_nonces"]  # type: ignore[assignment]
        self._verified_evidence_expiries = snapshot["evidence_expiries"]  # type: ignore[assignment]
        self._receipts = snapshot["receipts"]  # type: ignore[assignment]
        material = snapshot["material"]
        assert isinstance(material, dict)
        self._material.state = material["state"]
        self._material.rights = material["rights"]
        self._material.sanitized = material["sanitized"]
        self._material.normalized = material["normalized"]
        self._material._capture = material["capture"]
        self._material._nonces = material["nonces"]
        self._material._requests = material["requests"]
        self._material._bytes = material["bytes"]
        self._material._source_identifiers = material["source_identifiers"]
        self._material.audit = material["audit"]
        auth = snapshot["auth"]
        if self._auth is not None and isinstance(auth, dict):
            self._auth.state = auth["state"]
            self._auth.grant = auth["grant"]
            self._auth.receipt = auth["receipt"]
            self._auth.audit_codes = auth["audit_codes"]
            self._auth._used = auth["used"]
            self._auth._used_nonces = auth["used_nonces"]

    def _failure_state(self, snapshot: Mapping[str, object]) -> JobState | None:
        if (
            self.state != snapshot["state"]
            and self.state in {JobState.DENIED, JobState.QUARANTINED, JobState.EXPIRED}
        ):
            return self.state
        previous_material = snapshot["material"]
        assert isinstance(previous_material, dict)
        material_states = {
            MaterialState.ETHERNIAN_REVIEW: JobState.ETHERNIAN_REVIEW,
            MaterialState.DENIED: JobState.DENIED,
            MaterialState.QUARANTINED: JobState.QUARANTINED,
            MaterialState.EXPIRED: JobState.EXPIRED,
        }
        if (
            self._material.state != previous_material["state"]
            and self._material.state in material_states
        ):
            return material_states[self._material.state]
        if self._auth is not None:
            previous_auth = snapshot["auth"]
            assert isinstance(previous_auth, dict)
            auth_states = {
                AuthState.DENIED: JobState.DENIED,
                AuthState.EXPIRED: JobState.EXPIRED,
                AuthState.REVOKED: JobState.CANCELLED,
            }
            if self._auth.state != previous_auth["state"]:
                return auth_states.get(self._auth.state)
        return None

    def start(self, command_id: str, expected_version: int) -> CommandReceipt:
        return self._command(command_id, expected_version, {"start": True}, self._start, "JOB_STARTED")

    def _start(self) -> None:
        if self.state is not JobState.QUEUED:
            raise JobError("INVALID_STATE_TRANSITION")
        self.state = JobState.AUTH_PREFLIGHT_REQUIRED if self._auth else JobState.RIGHTS_REVIEW

    def submit_auth_preflight(
        self, command_id: str, expected_version: int, attestation: PreflightAttestation,
        binding: JobEvidenceBinding, *, grant: OpaqueGrant | None = None,
    ) -> CommandReceipt:
        payload = {"attestation": attestation, "binding": binding, "grant": grant}
        def op() -> None:
            if self.state is not JobState.AUTH_PREFLIGHT_REQUIRED or self._auth is None:
                raise JobError("INVALID_STATE_TRANSITION")
            self._verify_binding(binding, "AUTH_PREFLIGHT", attestation)
            self._auth.preflight(attestation)
            self._auth.await_user_auth()
            if self.request.auth_request and self.request.auth_request.user_actions:
                if grant is not None:
                    raise JobError("USER_ACTION_ATTESTATION_REQUIRED")
                self.state = JobState.USER_ACTION_REQUIRED
            else:
                if grant is None:
                    raise JobError("OPAQUE_GRANT_REQUIRED")
                self._auth.accept_grant(grant)
                self.state = JobState.RIGHTS_REVIEW
        return self._command(command_id, expected_version, payload, op, "AUTH_PREFLIGHT_VERIFIED")

    def submit_user_grant(
        self, command_id: str, expected_version: int, grant: OpaqueGrant,
        attestation: UserActionAttestation, binding: JobEvidenceBinding,
    ) -> CommandReceipt:
        payload = {"grant": grant, "attestation": attestation, "binding": binding}
        def op() -> None:
            if self.state is not JobState.USER_ACTION_REQUIRED or self._auth is None:
                raise JobError("INVALID_STATE_TRANSITION")
            self._verify_binding(binding, "USER_ACTION", attestation)
            self._auth.accept_grant(grant, user_action_attestation=attestation)
            self.state = JobState.RIGHTS_REVIEW
        return self._command(command_id, expected_version, payload, op, "USER_GRANT_VERIFIED")

    def review_rights(
        self, command_id: str, expected_version: int, rights: RightsEvidence,
        attestation: EthernianAttestation, binding: JobEvidenceBinding,
    ) -> CommandReceipt:
        payload = {"rights": rights, "attestation": attestation, "binding": binding}
        def op() -> None:
            if self.state is not JobState.RIGHTS_REVIEW:
                raise JobError("INVALID_STATE_TRANSITION")
            self._verify_binding(binding, "RIGHTS", attestation)
            self._material.evaluate_rights(rights, attestation)
            self.state = (JobState.COLLECTION_REVIEW if self._material.state is MaterialState.RIGHTS_EVALUATED
                          else JobState.ETHERNIAN_REVIEW)
        return self._command(command_id, expected_version, payload, op, "RIGHTS_REVIEWED")

    def review_collection(
        self, command_id: str, expected_version: int, posture: CollectionPosture,
        attestation: EthernianAttestation, binding: JobEvidenceBinding,
    ) -> CommandReceipt:
        payload = {"posture": posture, "attestation": attestation, "binding": binding}
        def op() -> None:
            if self.state is not JobState.COLLECTION_REVIEW:
                raise JobError("INVALID_STATE_TRANSITION")
            self._verify_binding(binding, "COLLECTION", attestation)
            self._material.pass_collection_policy(posture, attestation=attestation)
            self.state = (JobState.READY_TO_CAPTURE
                          if self._material.state is MaterialState.COLLECTION_POLICY_PASSED
                          else JobState.ETHERNIAN_REVIEW)
        return self._command(command_id, expected_version, payload, op, "COLLECTION_REVIEWED")

    def accept_sanitized_input(
        self, command_id: str, expected_version: int, envelope: SanitizedInputEnvelope,
        binding: JobEvidenceBinding,
    ) -> CommandReceipt:
        payload = {"envelope": envelope, "binding": binding}
        def op() -> None:
            if self.state is not JobState.READY_TO_CAPTURE:
                raise JobError("INVALID_STATE_TRANSITION")
            self._verify_binding(binding, "SANITIZED_INPUT", envelope)
            self._material.accept_sanitized_capture(envelope.capture)
            self.state = JobState.SANITIZE
        return self._command(command_id, expected_version, payload, op, "SANITIZED_INPUT_ACCEPTED")

    def confirm_sanitized(self, command_id: str, expected_version: int) -> CommandReceipt:
        def op() -> None:
            if self.state is not JobState.SANITIZE:
                raise JobError("INVALID_STATE_TRANSITION")
            self.state = JobState.NORMALIZE
        return self._command(
            command_id, expected_version, {"sanitized": True}, op, "SANITIZATION_CONFIRMED"
        )

    def normalize(self, command_id: str, expected_version: int) -> CommandReceipt:
        def op() -> None:
            if self.state is not JobState.NORMALIZE:
                raise JobError("INVALID_STATE_TRANSITION")
            self._material.normalize()
            self.state = JobState.ORIGINALITY_REVIEW
        return self._command(command_id, expected_version, {"normalize": True}, op, "MATERIAL_NORMALIZED")

    def approve_candidate(
        self, command_id: str, expected_version: int, candidate_content: str,
        evidence: tuple[ImprovementEvidence, ...], attestation: EthernianAttestation,
        binding: JobEvidenceBinding,
    ) -> CommandReceipt:
        payload = {"candidate_hash": _hash(candidate_content), "evidence": evidence,
                   "attestation": attestation, "binding": binding}
        def op() -> None:
            if self.state is not JobState.ORIGINALITY_REVIEW:
                raise JobError("INVALID_STATE_TRANSITION")
            self._verify_binding(binding, "ORIGINALITY", attestation)
            self._material.begin_originality_review()
            self.candidate = self._material.approve_candidate(
                candidate_content, improvement_evidence=evidence, attestation=attestation
            )
            self.state = JobState.ASSET_CANDIDATE
        return self._command(command_id, expected_version, payload, op, "ASSET_CANDIDATE_CREATED")

    def cancel(self, command_id: str, expected_version: int) -> CommandReceipt:
        def op() -> None:
            if self.state in TERMINAL:
                raise JobError("TERMINAL_STATE")
            self.state = JobState.CANCELLED
        return self._command(command_id, expected_version, {"cancel": True}, op, "JOB_CANCELLED")

    def recover(self) -> None:
        self.verify_ledger()
        self._check_live()
        if any(self._now() >= expiry for expiry in self._verified_evidence_expiries):
            self.state = JobState.EXPIRED
            self.version += 1
            self._append("EVIDENCE_EXPIRED_ON_RECOVERY", {})
            raise JobError("EVIDENCE_EXPIRED")
