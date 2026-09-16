from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class CertificationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
NONCE = re.compile(r"\A[0-9a-f-]{36}\Z")
SAFE_REVISION = re.compile(r"\A[0-9a-f]{7,64}\Z")
FORBIDDEN = re.compile(
    r"(?i)(password|passwd|authorization|cookie|bearer|api[-_]?key|session|private.?key|secret)"
)
MANDATORY_CHECKS = frozenset({
    "FULL_TESTS", "RUFF", "SCHEMA_MIGRATION", "THREAT_CONTROLS",
    "NO_RAW_SECRET", "NON_OWNED_CANDIDATES", "MANDATORY_VECTORS", "DETERMINISTIC_RERUN",
})
EXPECTED_VECTOR_STATES = {
    "NO_AUTH_REUSE": "ASSET_CANDIDATE",
    "AUTH_ADAPTIVE": "ASSET_CANDIDATE",
    "REVIEW_REQUIRED": "ETHERNIAN_REVIEW",
    "DENY": "DENIED",
    "EXPIRY_RECOVERY": "EXPIRED",
}


def canonical_json(value: object) -> bytes:
    def default(item: object) -> object:
        if is_dataclass(item):
            return asdict(item)
        if isinstance(item, datetime):
            if item.tzinfo is None:
                raise CertificationError("NAIVE_TIMESTAMP")
            return item.astimezone(UTC).isoformat(timespec="microseconds")
        raise TypeError(type(item).__name__)

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=default).encode()


def digest(value: object) -> str:
    return "sha256:" + sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class CheckArtifact:
    check_id: str
    artifact_digest: str
    git_revision: str
    build_id: str
    policy_version: str
    schema_version: str
    passed: bool
    expires_at: datetime
    nonce: str
    signature: str = ""


def _unsigned_artifact(item: CheckArtifact) -> bytes:
    return canonical_json(asdict(replace(item, signature="")))


class ArtifactSigner:
    """CI/reviewer-side helper. The release harness receives only its public key."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key

    def sign(self, artifact: CheckArtifact) -> CheckArtifact:
        unsigned = replace(artifact, signature="")
        return replace(unsigned, signature=self._key.sign(_unsigned_artifact(unsigned)).hex())


@dataclass(frozen=True)
class VectorResult:
    vector_id: str
    passed: bool
    terminal_state: str
    job_hash: str
    event_hash: str
    candidate_hash: str | None
    candidate_status: str | None
    license_obligations: tuple[str, ...] = ()
    evidence_hashes: tuple[str, ...] = ()
    trace_digest: str = ""

    def __post_init__(self) -> None:
        hashes = (self.job_hash, self.event_hash, self.trace_digest, *self.evidence_hashes)
        if self.candidate_hash:
            hashes += (self.candidate_hash,)
        if any(not DIGEST.fullmatch(item) for item in hashes):
            raise CertificationError("INVALID_VECTOR_DIGEST")
        if FORBIDDEN.search(canonical_json(asdict(self)).decode()):
            raise CertificationError("RAW_SECRET_OUTPUT_BLOCKED")


@dataclass(frozen=True)
class ReleasePlan:
    git_revision: str
    build_id: str
    policy_version: str
    schema_version: str
    required_vector_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseManifest:
    git_revision: str
    build_id: str
    policy_version: str
    schema_version: str
    test_vector_ids: tuple[str, ...]
    vector_results: tuple[VectorResult, ...]
    check_artifacts: tuple[CheckArtifact, ...]
    result: str
    generated_at: datetime
    expires_at: datetime
    nonce: str
    manifest_hash: str
    signature: str = ""


def _manifest_payload(item: ReleaseManifest) -> dict[str, object]:
    data = asdict(item)
    data["signature"] = ""
    data["manifest_hash"] = ""
    return data


class ReleaseSigner:
    """Offline release-authority helper; never pass this object into the harness."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key

    def sign(self, manifest: ReleaseManifest) -> ReleaseManifest:
        expected = digest(_manifest_payload(manifest))
        unsigned = replace(manifest, manifest_hash=expected, signature="")
        return replace(unsigned, signature=self._key.sign(canonical_json(_manifest_payload(unsigned))).hex())


class ReleaseCertificationHarness:
    """Executes deterministic API vectors and verifies externally signed release evidence."""

    def __init__(
        self, *, artifact_public_key: Ed25519PublicKey, release_public_key: Ed25519PublicKey,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._artifact_key = artifact_public_key
        self._release_key = release_public_key
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._used_nonces: set[str] = set()
        self._accepted_manifests: set[str] = set()

    def prepare(
        self, plan: ReleasePlan, vectors: object,
        artifacts: Sequence[CheckArtifact], *, generated_at: datetime, expires_at: datetime,
        nonce: str,
    ) -> ReleaseManifest:
        now = self._clock()
        if not SAFE_REVISION.fullmatch(plan.git_revision):
            raise CertificationError("INVALID_GIT_REVISION")
        if generated_at.tzinfo is None or expires_at.tzinfo is None or not generated_at <= now < expires_at:
            raise CertificationError("RELEASE_WINDOW_INVALID")
        if not NONCE.fullmatch(nonce) or nonce in self._used_nonces:
            raise CertificationError("RELEASE_REPLAY_BLOCKED")
        required = tuple(sorted(plan.required_vector_ids))
        if len(required) != len(set(required)) or not required:
            raise CertificationError("INVALID_VECTOR_SET")
        from .certification_vectors import CanonicalVectorSuite
        if type(vectors) is not CanonicalVectorSuite:
            raise CertificationError("UNTRUSTED_VECTOR_RUNNER")
        first = vectors.execute()
        second = vectors.execute()
        ids = tuple(item.vector_id for item in first)
        if ids != required or len(ids) != len(set(ids)):
            raise CertificationError("MANDATORY_VECTOR_MISSING_OR_DUPLICATE")
        if canonical_json(first) != canonical_json(second):
            raise CertificationError("NONDETERMINISTIC_VECTOR")
        self._validate_vectors(first)
        self._verify_artifacts(plan, artifacts, now)
        unsigned = ReleaseManifest(
            plan.git_revision, plan.build_id, plan.policy_version, plan.schema_version,
            ids, first, tuple(sorted(artifacts, key=lambda item: item.check_id)),
            "PASS", generated_at, expires_at, nonce, "", "",
        )
        return replace(unsigned, manifest_hash=digest(_manifest_payload(unsigned)))

    def accept(self, plan: ReleasePlan, manifest: ReleaseManifest) -> None:
        now = self._clock()
        if manifest.nonce in self._used_nonces or manifest.manifest_hash in self._accepted_manifests:
            raise CertificationError("RELEASE_REPLAY_BLOCKED")
        if now >= manifest.expires_at or manifest.generated_at > now:
            raise CertificationError("RELEASE_ATTESTATION_EXPIRED")
        if (manifest.git_revision, manifest.build_id, manifest.policy_version, manifest.schema_version) != (
            plan.git_revision, plan.build_id, plan.policy_version, plan.schema_version
        ) or manifest.test_vector_ids != tuple(sorted(plan.required_vector_ids)):
            raise CertificationError("RELEASE_BINDING_MISMATCH")
        if manifest.result != "PASS" or tuple(item.vector_id for item in manifest.vector_results) != manifest.test_vector_ids:
            raise CertificationError("RELEASE_RESULT_INVALID")
        self._validate_vectors(manifest.vector_results)
        self._verify_artifacts(plan, manifest.check_artifacts, now)
        expected = digest(_manifest_payload(manifest))
        if manifest.manifest_hash != expected:
            raise CertificationError("MANIFEST_TAMPERED")
        try:
            self._release_key.verify(bytes.fromhex(manifest.signature), canonical_json(_manifest_payload(manifest)))
        except (InvalidSignature, ValueError, TypeError):
            raise CertificationError("INVALID_RELEASE_SIGNATURE") from None
        self._used_nonces.add(manifest.nonce)
        self._used_nonces.update(item.nonce for item in manifest.check_artifacts)
        self._accepted_manifests.add(manifest.manifest_hash)

    @staticmethod
    def _validate_vectors(items: Sequence[VectorResult]) -> None:
        if any(not item.passed for item in items):
            raise CertificationError("VECTOR_FAILED")
        for item in items:
            if EXPECTED_VECTOR_STATES.get(item.vector_id) != item.terminal_state:
                raise CertificationError("VECTOR_TERMINAL_STATE_INVALID")
            if item.candidate_status and item.candidate_status != "CANDIDATE_NOT_OWNED_ASSET":
                raise CertificationError("OWNED_ASSET_PROMOTION_BLOCKED")
            expects_candidate = item.vector_id in {"NO_AUTH_REUSE", "AUTH_ADAPTIVE"}
            if expects_candidate != bool(item.candidate_hash and item.candidate_status):
                raise CertificationError("VECTOR_CANDIDATE_EVIDENCE_INVALID")
            if not item.evidence_hashes or not DIGEST.fullmatch(item.trace_digest):
                raise CertificationError("VECTOR_TRACE_EVIDENCE_INVALID")

    def _verify_artifacts(
        self, plan: ReleasePlan, artifacts: Sequence[CheckArtifact], now: datetime
    ) -> None:
        if len(artifacts) != len({item.check_id for item in artifacts}):
            raise CertificationError("DUPLICATE_CHECK_ARTIFACT")
        by_id = {item.check_id: item for item in artifacts}
        if set(by_id) != MANDATORY_CHECKS:
            raise CertificationError("MANDATORY_CHECK_ARTIFACT_MISSING")
        local_nonces: set[str] = set()
        for item in by_id.values():
            if not item.passed or not DIGEST.fullmatch(item.artifact_digest):
                raise CertificationError("CHECK_FAILED")
            if (item.git_revision, item.build_id, item.policy_version, item.schema_version) != (
                plan.git_revision, plan.build_id, plan.policy_version, plan.schema_version
            ):
                raise CertificationError("CHECK_BINDING_MISMATCH")
            if item.expires_at.tzinfo is None or now >= item.expires_at:
                raise CertificationError("CHECK_EXPIRED")
            if not NONCE.fullmatch(item.nonce) or item.nonce in local_nonces or item.nonce in self._used_nonces:
                raise CertificationError("CHECK_REPLAY_BLOCKED")
            try:
                self._artifact_key.verify(bytes.fromhex(item.signature), _unsigned_artifact(item))
            except (InvalidSignature, ValueError, TypeError):
                raise CertificationError("INVALID_CHECK_SIGNATURE") from None
            local_nonces.add(item.nonce)

    def _clock(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise CertificationError("NAIVE_CLOCK")
        return value.astimezone(UTC)


def manifest_json(manifest: ReleaseManifest) -> str:
    """Canonical, transport-safe representation of the signed manifest."""
    return canonical_json(asdict(manifest)).decode()
