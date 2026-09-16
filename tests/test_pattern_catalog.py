from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.pattern_catalog import (
    PatternCatalogError,
    PromotionDecision,
    PromotionVerifier,
    build_reuse_proof,
    catalog_revision,
    validate_catalog,
)

ROOT = Path(__file__).resolve().parents[1]


def candidates() -> list[dict]:
    return [
        json.loads(path.read_text())
        for path in sorted((ROOT / "knowledge/patterns/candidates").glob("*.json"))
    ]


def sign(private: Ed25519PrivateKey, decision: PromotionDecision) -> str:
    # TEST_VECTOR only; production code deliberately exposes verification only.
    raw = json.dumps(
        decision.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return base64.urlsafe_b64encode(private.sign(raw)).rstrip(b"=").decode()


def decision_for(
    package: dict, revision: str, nonce: str = "test-vector-nonce"
) -> PromotionDecision:
    canonical = lambda value: json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return PromotionDecision(
        pattern_id=package["pattern_id"],
        catalog_revision=revision,
        package_hash=package["package_hash"],
        evidence_digest=hashlib.sha256(canonical(package["evidence_hashes"])).hexdigest(),
        test_digest=hashlib.sha256(canonical(package["verification_test_ids"])).hexdigest(),
        policy="apf.public-pattern-promotion/1.0",
        expires_at="2030-01-01T00:00:00Z",
        nonce=nonce,
    )


def test_exactly_30_candidates_validate_with_real_evidence() -> None:
    packages = candidates()
    assert validate_catalog(packages, ROOT) == catalog_revision(packages)
    assert len(packages) == 30
    assert all(
        p["status"] == "ETHERNIAN_REVIEW_REQUIRED" and not p["owned_asset"] for p in packages
    )


def test_padding_and_duplicates_are_rejected() -> None:
    packages = candidates()
    packages[-1]["semantic_fingerprint"] = packages[0]["semantic_fingerprint"]
    with pytest.raises(PatternCatalogError, match="DUPLICATE_SEMANTIC_PATTERN"):
        validate_catalog(packages, ROOT)


def test_semantic_rename_padding_is_rejected() -> None:
    from apf.pattern_catalog import package_hash

    packages = candidates()
    packages[-1]["title"] = packages[0]["title"] + " renamed"
    packages[-1]["intent"] = packages[0]["intent"]
    packages[-1]["semantic_fingerprint"] = "1" * 64
    packages[-1]["package_hash"] = package_hash(packages[-1])
    with pytest.raises(PatternCatalogError, match="SEMANTICALLY_SIMILAR_PATTERN"):
        validate_catalog(packages, ROOT)


def test_near_duplicate_body_and_fake_anchor_are_rejected() -> None:
    from apf.pattern_catalog import package_hash

    packages = candidates()
    body_fields = ("problem", "context", "solution", "security", "privacy")
    for field in body_fields:
        packages[-1][field] = packages[0][field]
    packages[-1]["solution"] += " Additional wording."
    packages[-1]["package_hash"] = package_hash(packages[-1])
    with pytest.raises(PatternCatalogError, match="BOILERPLATE_FIELD_SIMILARITY"):
        validate_catalog(packages, ROOT)

    packages = candidates()
    packages[0]["evidence_anchors"]["source_symbol"] = "InventedSymbol"
    packages[0]["package_hash"] = package_hash(packages[0])
    with pytest.raises(PatternCatalogError, match="SOURCE_SYMBOL_ANCHOR_MISSING"):
        validate_catalog(packages, ROOT)


def test_evidence_tamper_is_rejected() -> None:
    packages = candidates()
    packages[0]["evidence_hashes"][packages[0]["source_refs"][0]] = "0" * 64
    with pytest.raises(PatternCatalogError, match="EVIDENCE_HASH_MISMATCH"):
        validate_catalog(packages, ROOT)


def test_candidate_reuse_fails_closed_before_promotion() -> None:
    with pytest.raises(PatternCatalogError, match="CANDIDATE_REUSE_FORBIDDEN"):
        build_reuse_proof(candidates()[:3], project_id="pre-promotion-negative-proof")


def test_test_vector_approves_public_pattern_but_not_owned_asset() -> None:
    packages = candidates()
    revision = validate_catalog(packages, ROOT)
    private = Ed25519PrivateKey.generate()
    verifier = PromotionVerifier(
        private.public_key(), now_provider=lambda: datetime(2029, 1, 1, tzinfo=UTC)
    )
    approved = []
    for index, package in enumerate(packages[:3]):
        decision = decision_for(package, revision, f"test-vector-{index}")
        approved.append(
            verifier.verify(
                package, decision, sign(private, decision), expected_catalog_revision=revision
            )
        )
    proof = build_reuse_proof(approved, project_id="test-vector-three-pattern-reuse")
    assert proof["pattern_ids"] == sorted(p["pattern_id"] for p in approved)
    assert proof["owned_asset"] is False
    assert all(p["status"] == "PUBLIC_PATTERN_APPROVED" and not p["owned_asset"] for p in approved)


def test_promotion_rejects_wrong_catalog_expiry_and_replay() -> None:
    package = candidates()[0]
    revision = catalog_revision(candidates())
    private = Ed25519PrivateKey.generate()
    now = datetime(2029, 1, 1, tzinfo=UTC)
    verifier = PromotionVerifier(private.public_key(), now_provider=lambda: now)
    decision = decision_for(package, revision)
    signature = sign(private, decision)
    with pytest.raises(PatternCatalogError, match="CATALOG_BINDING"):
        verifier.verify(package, decision, signature, expected_catalog_revision="0" * 64)
    verifier.verify(package, decision, signature, expected_catalog_revision=revision)
    with pytest.raises(PatternCatalogError, match="NONCE_REPLAYED"):
        verifier.verify(package, decision, signature, expected_catalog_revision=revision)
    expired = PromotionDecision(
        **{
            **decision.payload(),
            "nonce": "expired",
            "expires_at": (now - timedelta(seconds=1)).isoformat(),
        }
    )
    with pytest.raises(PatternCatalogError, match="PROMOTION_EXPIRED"):
        verifier.verify(
            package, expired, sign(private, expired), expected_catalog_revision=revision
        )


def test_wrong_key_and_package_binding_are_rejected() -> None:
    package = candidates()[0]
    revision = catalog_revision(candidates())
    signer = Ed25519PrivateKey.generate()
    verifier = PromotionVerifier(
        Ed25519PrivateKey.generate().public_key(),
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=UTC),
    )
    decision = decision_for(package, revision)
    with pytest.raises(PatternCatalogError, match="SIGNATURE_INVALID"):
        verifier.verify(
            package, decision, sign(signer, decision), expected_catalog_revision=revision
        )
    bad = PromotionDecision(**{**decision.payload(), "nonce": "tampered", "package_hash": "f" * 64})
    with pytest.raises(PatternCatalogError, match="PACKAGE_BINDING"):
        verifier.verify(package, bad, sign(signer, bad), expected_catalog_revision=revision)
