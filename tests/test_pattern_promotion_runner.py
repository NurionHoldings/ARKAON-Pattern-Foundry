from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.pattern_catalog import PromotionDecision, catalog_revision, validate_catalog
from apf.pattern_promotion_runner import (
    PatternPromotionPolicy,
    PatternPromotionRunner,
    PromotionOutcome,
)

ROOT = Path(__file__).resolve().parents[1]


def candidates() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "knowledge/patterns/candidates").glob("*.json"))
    ]


def sign(private: Ed25519PrivateKey, decision: PromotionDecision) -> str:
    raw = json.dumps(
        decision.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return base64.urlsafe_b64encode(private.sign(raw)).rstrip(b"=").decode()


def decision_for(package: dict, revision: str, nonce: str) -> PromotionDecision:
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


def _policy(tmp_path: Path, *, private: Ed25519PrivateKey, accept_test_vector: bool) -> PatternPromotionPolicy:
    document = json.loads((ROOT / "config" / "arkaon-pattern-promotion.json").read_text(encoding="utf-8"))
    document["ethernian_public_key_b64"] = base64.urlsafe_b64encode(
        private.public_key().public_bytes_raw()
    ).rstrip(b"=").decode()
    document["accept_test_vector_decisions"] = accept_test_vector
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return PatternPromotionPolicy.load(path)


def test_runner_reports_all_pending_without_manifest(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    report = PatternPromotionRunner(
        foundry_root=ROOT,
        policy=_policy(tmp_path, private=private, accept_test_vector=False),
        manifest_path=tmp_path / "empty-manifest.json",
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=UTC),
    ).run(dry_run=True)
    assert report.candidate_count == 30
    assert report.verified_count == 0
    assert report.pending_count == 30
    assert report.reuse_proof is None


def test_runner_verifies_test_vector_and_builds_reuse_proof(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    packages = candidates()
    revision = validate_catalog(packages, ROOT)
    manifest = {
        "schema_version": "apf.pattern-promotion-manifest/v1",
        "catalog_revision": revision,
        "decisions": [],
    }
    for index, package in enumerate(packages[:3]):
        decision = decision_for(package, revision, f"test-vector-{index}")
        manifest["decisions"].append(
            {
                "pattern_id": package["pattern_id"],
                "source": "TEST_VECTOR",
                "decision": decision.payload(),
                "signature": sign(private, decision),
            }
        )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = PatternPromotionRunner(
        foundry_root=ROOT,
        policy=_policy(tmp_path, private=private, accept_test_vector=True),
        manifest_path=manifest_path,
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=UTC),
    ).run(dry_run=True)
    assert report.verified_count == 3
    assert report.pending_count == 27
    assert report.reuse_proof is not None
    assert report.reuse_proof["owned_asset"] is False
    assert all(item.outcome is PromotionOutcome.VERIFIED for item in report.results[:3])


def test_runner_rejects_test_vector_when_disabled(tmp_path: Path) -> None:
    private = Ed25519PrivateKey.generate()
    package = candidates()[0]
    revision = catalog_revision(candidates())
    decision = decision_for(package, revision, "test-vector-0")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "apf.pattern-promotion-manifest/v1",
                "decisions": [
                    {
                        "pattern_id": package["pattern_id"],
                        "source": "TEST_VECTOR",
                        "decision": decision.payload(),
                        "signature": sign(private, decision),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = PatternPromotionRunner(
        foundry_root=ROOT,
        policy=_policy(tmp_path, private=private, accept_test_vector=False),
        manifest_path=manifest_path,
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=UTC),
    ).run(dry_run=True)
    assert report.rejected_count == 1
    assert report.results[0].message == "TEST_VECTOR decisions are disabled by policy"
