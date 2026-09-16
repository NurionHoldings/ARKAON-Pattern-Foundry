from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class PatternCatalogError(ValueError):
    """Raised when a candidate, promotion decision, or reuse proof is unsafe."""


REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "pattern_id",
        "version",
        "title",
        "intent",
        "problem",
        "context",
        "forces",
        "solution",
        "invariants",
        "failure_modes",
        "security",
        "privacy",
        "license_provenance",
        "evidence_hashes",
        "source_refs",
        "test_refs",
        "verification_test_ids",
        "reuse_constraints",
        "applies_when",
        "not_when",
        "evidence_anchors",
        "status",
        "owned_asset",
        "semantic_fingerprint",
        "package_hash",
    }
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def package_hash(package: dict[str, Any]) -> str:
    return _sha256(_canonical({k: v for k, v in package.items() if k != "package_hash"}))


def catalog_revision(packages: Iterable[dict[str, Any]]) -> str:
    values = sorted((p["pattern_id"], p["package_hash"]) for p in packages)
    return _sha256(_canonical(values))


def _require_text(value: Any, code: str, *, minimum: int = 12) -> None:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise PatternCatalogError(code)


def validate_catalog(packages: list[dict[str, Any]], root: Path) -> str:
    if len(packages) != 30:
        raise PatternCatalogError("CATALOG_MUST_CONTAIN_EXACTLY_30_PATTERNS")
    ids: set[str] = set()
    fingerprints: set[str] = set()
    semantic_tokens: list[set[str]] = []
    body_tokens: list[set[str]] = []
    field_fingerprints: set[str] = set()
    sentence_counts: dict[str, int] = {}
    coverage: set[str] = set()
    for package in packages:
        if set(package) != REQUIRED_FIELDS:
            raise PatternCatalogError("PACKAGE_FIELDS_INVALID")
        if package["schema_version"] != "apf.pattern-candidate/1.0":
            raise PatternCatalogError("SCHEMA_VERSION_INVALID")
        if package["status"] != "ETHERNIAN_REVIEW_REQUIRED" or package["owned_asset"] is not False:
            raise PatternCatalogError("CANDIDATE_STATUS_REQUIRED")
        if package["pattern_id"] in ids:
            raise PatternCatalogError("DUPLICATE_PATTERN_ID")
        if package["semantic_fingerprint"] in fingerprints:
            raise PatternCatalogError("DUPLICATE_SEMANTIC_PATTERN")
        ids.add(package["pattern_id"])
        fingerprints.add(package["semantic_fingerprint"])
        tokens = set(re.findall(r"[a-z0-9]+", f"{package['title']} {package['intent']}".lower()))
        for prior in semantic_tokens:
            if len(tokens & prior) / len(tokens | prior) >= 0.82:
                raise PatternCatalogError("SEMANTICALLY_SIMILAR_PATTERN")
        semantic_tokens.append(tokens)
        substantive = [
            package[field] for field in ("problem", "context", "solution", "security", "privacy")
        ]
        field_fingerprint = _sha256(_canonical(substantive))
        if field_fingerprint in field_fingerprints:
            raise PatternCatalogError("BOILERPLATE_FIELD_DUPLICATION")
        field_fingerprints.add(field_fingerprint)
        body = set(re.findall(r"[a-z0-9]+", " ".join(substantive).lower()))
        for prior in body_tokens:
            if len(body & prior) / len(body | prior) >= 0.88:
                raise PatternCatalogError("BOILERPLATE_FIELD_SIMILARITY")
        body_tokens.append(body)
        for sentence in substantive:
            normalized = " ".join(re.findall(r"[a-z0-9]+", sentence.lower()))
            sentence_counts[normalized] = sentence_counts.get(normalized, 0) + 1
            if sentence_counts[normalized] > 2:
                raise PatternCatalogError("REPEATED_SENTENCE_RATIO_EXCEEDED")
        for field in ("intent", "problem", "context", "solution", "security", "privacy"):
            _require_text(package[field], f"{field.upper()}_REQUIRED")
        for field in ("forces", "invariants", "failure_modes", "reuse_constraints"):
            if not isinstance(package[field], list) or len(package[field]) < 2:
                raise PatternCatalogError(f"{field.upper()}_REQUIRED")
        _require_text(package["applies_when"], "APPLIES_WHEN_REQUIRED")
        _require_text(package["not_when"], "NOT_WHEN_REQUIRED")
        refs = package["source_refs"] + package["test_refs"]
        if not package["source_refs"] or not package["test_refs"]:
            raise PatternCatalogError("SOURCE_AND_TEST_REFS_REQUIRED")
        for ref in refs:
            if ref.startswith("/") or ".." in Path(ref).parts or not (root / ref).is_file():
                raise PatternCatalogError("EVIDENCE_REFERENCE_INVALID")
            expected = _sha256((root / ref).read_bytes())
            if package["evidence_hashes"].get(ref) != expected:
                raise PatternCatalogError("EVIDENCE_HASH_MISMATCH")
        if set(package["evidence_hashes"]) != set(refs):
            raise PatternCatalogError("UNBOUND_EVIDENCE_HASH")
        anchors = package["evidence_anchors"]
        if set(anchors) != {"source_symbol", "test_name"}:
            raise PatternCatalogError("EVIDENCE_ANCHORS_INVALID")
        source_text = (root / package["source_refs"][0]).read_text()
        test_text = (root / package["test_refs"][0]).read_text()
        if not re.search(rf"\b{re.escape(anchors['source_symbol'])}\b", source_text):
            raise PatternCatalogError("SOURCE_SYMBOL_ANCHOR_MISSING")
        if not re.search(rf"def {re.escape(anchors['test_name'])}\(", test_text):
            raise PatternCatalogError("TEST_ASSERTION_ANCHOR_MISSING")
        if package["license_provenance"] != {
            "license": "INTERNAL_PROPRIETARY",
            "origin": "ARKAON_IMPLEMENTED_INTERNAL",
            "external_material_included": False,
        }:
            raise PatternCatalogError("LICENSE_PROVENANCE_INVALID")
        if package_hash(package) != package["package_hash"]:
            raise PatternCatalogError("PACKAGE_HASH_MISMATCH")
        coverage.update(package["source_refs"])
    if len(coverage) < 15:
        raise PatternCatalogError("CATALOG_COVERAGE_TOO_NARROW")
    return catalog_revision(packages)


@dataclass(frozen=True)
class PromotionDecision:
    pattern_id: str
    catalog_revision: str
    package_hash: str
    evidence_digest: str
    test_digest: str
    policy: str
    expires_at: str
    nonce: str
    decision: str = "PUBLIC_PATTERN_APPROVED"
    owned_asset: bool = False

    def payload(self) -> dict[str, Any]:
        return self.__dict__.copy()


class PromotionVerifier:
    """Public-key-only verifier. This component has no signing capability."""

    def __init__(
        self, public_key: Ed25519PublicKey, *, now_provider: Callable[[], datetime]
    ) -> None:
        self._public_key = public_key
        self._now_provider = now_provider
        self._used_nonces: set[str] = set()

    def verify(
        self,
        package: dict[str, Any],
        decision: PromotionDecision,
        signature: str,
        *,
        expected_catalog_revision: str,
    ) -> dict[str, Any]:
        if package_hash(package) != package.get("package_hash"):
            raise PatternCatalogError("PROMOTION_PACKAGE_HASH_INVALID")
        if (
            package.get("status") != "ETHERNIAN_REVIEW_REQUIRED"
            or package.get("owned_asset") is not False
        ):
            raise PatternCatalogError("PROMOTION_REQUIRES_CANDIDATE")
        if (
            decision.pattern_id != package["pattern_id"]
            or decision.package_hash != package["package_hash"]
        ):
            raise PatternCatalogError("PROMOTION_PACKAGE_BINDING_MISMATCH")
        if decision.catalog_revision != expected_catalog_revision:
            raise PatternCatalogError("PROMOTION_CATALOG_BINDING_MISMATCH")
        evidence = _sha256(_canonical(package["evidence_hashes"]))
        tests = _sha256(_canonical(package["verification_test_ids"]))
        if decision.evidence_digest != evidence or decision.test_digest != tests:
            raise PatternCatalogError("PROMOTION_EVIDENCE_BINDING_MISMATCH")
        if decision.policy != "apf.public-pattern-promotion/1.0":
            raise PatternCatalogError("PROMOTION_POLICY_INVALID")
        if decision.decision != "PUBLIC_PATTERN_APPROVED" or decision.owned_asset:
            raise PatternCatalogError("PROMOTION_DECISION_INVALID")
        try:
            expires = datetime.fromisoformat(decision.expires_at)
        except ValueError as exc:
            raise PatternCatalogError("PROMOTION_EXPIRY_INVALID") from exc
        checked_at = self._now_provider()
        if checked_at.tzinfo is None:
            raise PatternCatalogError("PROMOTION_VERIFICATION_TIME_INVALID")
        if expires.tzinfo is None or checked_at.astimezone(UTC) >= expires.astimezone(UTC):
            raise PatternCatalogError("PROMOTION_EXPIRED")
        if not decision.nonce or decision.nonce in self._used_nonces:
            raise PatternCatalogError("PROMOTION_NONCE_REPLAYED")
        try:
            raw = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            self._public_key.verify(raw, _canonical(decision.payload()))
        except (binascii.Error, InvalidSignature, ValueError) as exc:
            raise PatternCatalogError("PROMOTION_SIGNATURE_INVALID") from exc
        self._used_nonces.add(decision.nonce)
        return {**package, "status": "PUBLIC_PATTERN_APPROVED", "owned_asset": False}


def build_reuse_proof(approved: list[dict[str, Any]], *, project_id: str) -> dict[str, Any]:
    if len(approved) < 3:
        raise PatternCatalogError("THREE_APPROVED_PATTERNS_REQUIRED")
    if any(p.get("status") != "PUBLIC_PATTERN_APPROVED" for p in approved):
        raise PatternCatalogError("CANDIDATE_REUSE_FORBIDDEN")
    ids = sorted(p["pattern_id"] for p in approved)
    if len(set(ids)) != len(ids):
        raise PatternCatalogError("DUPLICATE_REUSE_PATTERN")
    return {
        "schema_version": "apf.reuse-proof/1.0",
        "project_id": project_id,
        "pattern_ids": ids,
        "proof_digest": _sha256(
            _canonical([(p["pattern_id"], p["package_hash"]) for p in approved])
        ),
        "owned_asset": False,
    }
