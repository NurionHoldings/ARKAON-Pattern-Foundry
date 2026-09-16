from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.certification_vectors import CanonicalVectorSuite
from apf.release_certification import (
    MANDATORY_CHECKS,
    ArtifactSigner,
    CertificationError,
    CheckArtifact,
    ReleaseCertificationHarness,
    ReleasePlan,
    ReleaseSigner,
    VectorResult,
    digest,
    manifest_json,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
REV = "a" * 40


def key(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def plan() -> ReleasePlan:
    return ReleasePlan(
        REV, "build-036", "apf-policy-v0.1", "sqlite-v1",
        ("AUTH_ADAPTIVE", "DENY", "EXPIRY_RECOVERY", "NO_AUTH_REUSE", "REVIEW_REQUIRED"),
    )


def artifacts(p: ReleasePlan, signer: ArtifactSigner):
    return tuple(
        signer.sign(CheckArtifact(
            check, digest({"check": check, "evidence": "verified"}), p.git_revision,
            p.build_id, p.policy_version, p.schema_version, True, LATER,
            f"00000000-0000-0000-0000-{index:012d}",
        ))
        for index, check in enumerate(sorted(MANDATORY_CHECKS), 1)
    )


def vectors():
    return CanonicalVectorSuite()


def setup():
    artifact_key, release_key = key(7), key(8)
    harness = ReleaseCertificationHarness(
        artifact_public_key=artifact_key.public_key(), release_public_key=release_key.public_key(),
        now_provider=lambda: NOW,
    )
    p = plan()
    return harness, p, artifacts(p, ArtifactSigner(artifact_key)), ReleaseSigner(release_key)


def prepared():
    harness, p, proof, signer = setup()
    manifest = harness.prepare(
        p, vectors(), proof, generated_at=NOW, expires_at=LATER,
        nonce="90000000-0000-0000-0000-000000000001",
    )
    return harness, p, signer.sign(manifest)


def test_actual_api_vectors_produce_signed_canonical_release_manifest():
    harness, p, signed = prepared()
    harness.accept(p, signed)
    assert signed.result == "PASS"
    assert signed.manifest_hash.startswith("sha256:")
    assert manifest_json(signed) == manifest_json(signed)
    assert all(item.candidate_status != "OWNED_ASSET" for item in signed.vector_results)


@pytest.mark.parametrize("field", ["git_revision", "build_id", "policy_version", "schema_version"])
def test_release_binding_changes_fail_closed(field):
    harness, p, signed = prepared()
    with pytest.raises(CertificationError, match="RELEASE_BINDING_MISMATCH"):
        harness.accept(replace(p, **{field: getattr(p, field) + "x"}), signed)


def test_signature_tamper_wrong_key_expiry_and_replay_fail_closed():
    harness, p, signed = prepared()
    with pytest.raises(CertificationError, match="RELEASE_RESULT_INVALID"):
        harness.accept(p, replace(signed, result="FAIL"))
    wrong = ReleaseSigner(key(9)).sign(replace(signed, signature=""))
    with pytest.raises(CertificationError, match="INVALID_RELEASE_SIGNATURE"):
        harness.accept(p, wrong)
    harness.accept(p, signed)
    with pytest.raises(CertificationError, match="RELEASE_REPLAY_BLOCKED"):
        harness.accept(p, signed)
    expired, p2, signed2 = prepared()
    expired._now = lambda: LATER
    with pytest.raises(CertificationError, match="RELEASE_ATTESTATION_EXPIRED"):
        expired.accept(p2, signed2)


def test_missing_duplicate_failed_and_badly_bound_check_artifacts_fail_closed():
    harness, p, proof, _ = setup()
    kwargs = {"generated_at": NOW, "expires_at": LATER, "nonce": "90000000-0000-0000-0000-000000000002"}
    with pytest.raises(CertificationError, match="MANDATORY_CHECK_ARTIFACT_MISSING"):
        harness.prepare(p, vectors(), proof[:-1], **kwargs)
    with pytest.raises(CertificationError, match="DUPLICATE_CHECK_ARTIFACT"):
        harness.prepare(p, vectors(), proof + (proof[0],), **kwargs)
    with pytest.raises(CertificationError, match="CHECK_FAILED"):
        harness.prepare(p, vectors(), (replace(proof[0], passed=False), *proof[1:]), **kwargs)
    with pytest.raises(CertificationError, match="CHECK_BINDING_MISMATCH"):
        harness.prepare(p, vectors(), (replace(proof[0], build_id="other"), *proof[1:]), **kwargs)


def test_arbitrary_vector_callbacks_are_not_trusted():
    harness, p, proof, _ = setup()
    kwargs = {"generated_at": NOW, "expires_at": LATER, "nonce": "90000000-0000-0000-0000-000000000003"}
    with pytest.raises(CertificationError, match="UNTRUSTED_VECTOR_RUNNER"):
        harness.prepare(p, (), proof, **kwargs)
    with pytest.raises(CertificationError, match="UNTRUSTED_VECTOR_RUNNER"):
        harness.prepare(p, (lambda: None,), proof, **kwargs)


def test_invalid_artifact_signature_and_raw_secret_output_are_blocked():
    harness, p, proof, _ = setup()
    kwargs = {"generated_at": NOW, "expires_at": LATER, "nonce": "90000000-0000-0000-0000-000000000004"}
    with pytest.raises(CertificationError, match="INVALID_CHECK_SIGNATURE"):
        harness.prepare(p, vectors(), (replace(proof[0], signature="00" * 64), *proof[1:]), **kwargs)
    with pytest.raises(CertificationError, match="RAW_SECRET_OUTPUT_BLOCKED"):
        VectorResult("password", True, "PASS", "sha256:" + "1" * 64,
                     "sha256:" + "2" * 64, None, None, (), (), "sha256:" + "3" * 64)


def test_release_signer_cannot_bypass_semantic_or_check_evidence_gate():
    harness, p, signed = prepared()
    signer = ReleaseSigner(key(8))
    missing = signer.sign(replace(signed, check_artifacts=(), signature=""))
    with pytest.raises(CertificationError, match="MANDATORY_CHECK_ARTIFACT_MISSING"):
        harness.accept(p, missing)
    promoted_result = replace(signed.vector_results[0], candidate_status="OWNED_ASSET")
    promoted = signer.sign(replace(
        signed, vector_results=(promoted_result, *signed.vector_results[1:]), signature=""
    ))
    with pytest.raises(CertificationError, match="OWNED_ASSET_PROMOTION_BLOCKED"):
        harness.accept(p, promoted)
    fake_terminal = replace(signed.vector_results[0], terminal_state="RIGHTS_REVIEW")
    skipped = signer.sign(replace(
        signed, vector_results=(fake_terminal, *signed.vector_results[1:]), signature=""
    ))
    with pytest.raises(CertificationError, match="VECTOR_TERMINAL_STATE_INVALID"):
        harness.accept(p, skipped)
    with pytest.raises(CertificationError, match="INVALID_VECTOR_DIGEST"):
        replace(signed.vector_results[0], candidate_hash="sha256:" + "f" * 64,
                trace_digest="")
