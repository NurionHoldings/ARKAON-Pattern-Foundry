"""Pattern catalog validation, external promotion verification, and reuse proof assembly."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .pattern_catalog import (
    PatternCatalogError,
    PromotionDecision,
    PromotionVerifier,
    build_reuse_proof,
    validate_catalog,
)


class PromotionRunnerRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PromotionOutcome(str, Enum):
    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PatternPromotionPolicy:
    production_promotion_allowed: bool = False
    minimum_reuse_patterns: int = 3
    ethernian_public_key_b64: str | None = None
    accept_test_vector_decisions: bool = False

    @classmethod
    def load(cls, path: Path) -> PatternPromotionPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-pattern-promotion/v1":
            raise PromotionRunnerRejected("POLICY_SCHEMA", "unsupported pattern promotion schema")
        if document.get("production_promotion_allowed"):
            raise PromotionRunnerRejected("POLICY_FORBIDDEN", "production promotion must remain external")
        minimum = int(document.get("minimum_reuse_patterns", 3))
        if minimum < 3:
            raise PromotionRunnerRejected("POLICY_INVALID", "minimum reuse patterns must be at least 3")
        return cls(
            production_promotion_allowed=bool(document.get("production_promotion_allowed")),
            minimum_reuse_patterns=minimum,
            ethernian_public_key_b64=document.get("ethernian_public_key_b64"),
            accept_test_vector_decisions=bool(document.get("accept_test_vector_decisions")),
        )


@dataclass(frozen=True)
class PromotionAttemptResult:
    pattern_id: str
    outcome: PromotionOutcome
    source: str
    message: str


@dataclass(frozen=True)
class PatternPromotionReport:
    foundry_root: Path
    evaluated_at: datetime
    catalog_revision: str
    candidate_count: int
    verified_count: int
    pending_count: int
    rejected_count: int
    reuse_proof: dict[str, object] | None
    results: tuple[PromotionAttemptResult, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.pattern-promotion-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "catalog_revision": self.catalog_revision,
            "candidate_count": self.candidate_count,
            "verified_count": self.verified_count,
            "pending_count": self.pending_count,
            "rejected_count": self.rejected_count,
            "reuse_proof": self.reuse_proof,
            "report_digest": self.report_digest,
            "results": [
                {
                    "pattern_id": item.pattern_id,
                    "outcome": item.outcome.value,
                    "source": item.source,
                    "message": item.message,
                }
                for item in self.results
            ],
        }


def load_candidates(foundry_root: Path) -> list[dict[str, Any]]:
    directory = foundry_root / "knowledge" / "patterns" / "candidates"
    if not directory.is_dir():
        raise PromotionRunnerRejected("CATALOG_MISSING", "pattern candidate directory is missing")
    packages = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))
    ]
    return packages


def _load_public_key(policy: PatternPromotionPolicy) -> Ed25519PublicKey | None:
    if not policy.ethernian_public_key_b64:
        return None
    try:
        raw = base64.urlsafe_b64decode(policy.ethernian_public_key_b64 + "=" * (-len(policy.ethernian_public_key_b64) % 4))
        return Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        raise PromotionRunnerRejected("PUBLIC_KEY_INVALID", "ethernian public key is invalid") from exc


def _report_digest(document: dict[str, object]) -> str:
    from hashlib import sha256

    payload = {key: value for key, value in document.items() if key != "report_digest"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return sha256(canonical).hexdigest()


class PatternPromotionRunner:
    def __init__(
        self,
        *,
        foundry_root: Path,
        policy: PatternPromotionPolicy | None = None,
        manifest_path: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.foundry_root = foundry_root
        self.policy = policy or PatternPromotionPolicy.load(
            foundry_root / "config" / "arkaon-pattern-promotion.json"
        )
        self.manifest_path = manifest_path
        self._now_provider = now_provider or (lambda: datetime.now(tz=UTC))

    def run(self, *, dry_run: bool = False) -> PatternPromotionReport:
        packages = load_candidates(self.foundry_root)
        revision = validate_catalog(packages, self.foundry_root)
        manifest_path = self.manifest_path or (
            self.foundry_root / "config" / "pattern-promotion-manifest.json"
        )
        manifest = self._load_manifest(manifest_path, expected_revision=revision)
        public_key = _load_public_key(self.policy)
        verifier = PromotionVerifier(public_key, now_provider=self._now_provider) if public_key else None
        manifest_entries = {
            str(item["pattern_id"]): item for item in manifest.get("decisions") or []
        }
        results: list[PromotionAttemptResult] = []
        approved: list[dict[str, Any]] = []
        for package in packages:
            pattern_id = str(package["pattern_id"])
            entry = manifest_entries.get(pattern_id)
            if entry is None:
                results.append(
                    PromotionAttemptResult(
                        pattern_id=pattern_id,
                        outcome=PromotionOutcome.PENDING,
                        source="NONE",
                        message="awaiting external eternian promotion decision",
                    )
                )
                continue
            source = str(entry.get("source", "EXTERNAL_ETHERNIAN"))
            if source == "TEST_VECTOR" and not self.policy.accept_test_vector_decisions:
                results.append(
                    PromotionAttemptResult(
                        pattern_id=pattern_id,
                        outcome=PromotionOutcome.REJECTED,
                        source=source,
                        message="TEST_VECTOR decisions are disabled by policy",
                    )
                )
                continue
            if verifier is None:
                results.append(
                    PromotionAttemptResult(
                        pattern_id=pattern_id,
                        outcome=PromotionOutcome.REJECTED,
                        source=source,
                        message="ethernian public key is not configured",
                    )
                )
                continue
            try:
                decision = PromotionDecision(**dict(entry["decision"]))
                approved_package = verifier.verify(
                    package,
                    decision,
                    str(entry["signature"]),
                    expected_catalog_revision=revision,
                )
            except (PatternCatalogError, KeyError, TypeError) as exc:
                code = getattr(exc, "args", ["PROMOTION_REJECTED"])[0]
                results.append(
                    PromotionAttemptResult(
                        pattern_id=pattern_id,
                        outcome=PromotionOutcome.REJECTED,
                        source=source,
                        message=str(code),
                    )
                )
                continue
            approved.append(approved_package)
            results.append(
                PromotionAttemptResult(
                    pattern_id=pattern_id,
                    outcome=PromotionOutcome.VERIFIED,
                    source=source,
                    message="public pattern promotion verified",
                )
            )
        verified_count = sum(1 for item in results if item.outcome is PromotionOutcome.VERIFIED)
        pending_count = sum(1 for item in results if item.outcome is PromotionOutcome.PENDING)
        rejected_count = sum(1 for item in results if item.outcome is PromotionOutcome.REJECTED)
        reuse_proof: dict[str, object] | None = None
        if verified_count >= self.policy.minimum_reuse_patterns:
            reuse_proof = build_reuse_proof(approved, project_id="ARKAON_FOUNDRY")
        evaluated_at = self._now_provider()
        report_without_digest = PatternPromotionReport(
            foundry_root=self.foundry_root,
            evaluated_at=evaluated_at,
            catalog_revision=revision,
            candidate_count=len(packages),
            verified_count=verified_count,
            pending_count=pending_count,
            rejected_count=rejected_count,
            reuse_proof=reuse_proof,
            results=tuple(results),
            report_digest="",
        )
        document = report_without_digest.to_document()
        digest = _report_digest(document)
        report = PatternPromotionReport(
            foundry_root=self.foundry_root,
            evaluated_at=evaluated_at,
            catalog_revision=revision,
            candidate_count=len(packages),
            verified_count=verified_count,
            pending_count=pending_count,
            rejected_count=rejected_count,
            reuse_proof=reuse_proof,
            results=tuple(results),
            report_digest=digest,
        )
        if not dry_run:
            state_dir = self.foundry_root / "state" / "pattern-promotion"
            state_dir.mkdir(parents=True, exist_ok=True)
            stamp = evaluated_at.astimezone(UTC).strftime("%Y-%m-%d")
            target = state_dir / f"{stamp}-{digest[:16]}.json"
            target.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return report

    def _load_manifest(self, path: Path, *, expected_revision: str) -> dict[str, object]:
        if not path.is_file():
            return {"schema_version": "apf.pattern-promotion-manifest/v1", "decisions": []}
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.pattern-promotion-manifest/v1":
            raise PromotionRunnerRejected("MANIFEST_SCHEMA", "unsupported promotion manifest schema")
        bound_revision = document.get("catalog_revision")
        if bound_revision and bound_revision != expected_revision:
            raise PromotionRunnerRejected(
                "MANIFEST_CATALOG_MISMATCH",
                "promotion manifest catalog revision does not match current catalog",
            )
        return document
