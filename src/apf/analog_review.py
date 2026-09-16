from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .analog_synthesis import validate_analog_manifest


class AnalogReviewError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReviewVerdict(StrEnum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    DENY = "DENY"


class ReviewOutcome(StrEnum):
    APPROVED_FOR_PATTERN_PROMOTION = "APPROVED_FOR_PATTERN_PROMOTION"
    ETHERNIAN_REVIEW_REQUIRED = "ETHERNIAN_REVIEW_REQUIRED"
    DENIED = "DENIED"


REQUIRED_CHECKS = (
    "LINEAGE_INDEPENDENCE",
    "OFFICIAL_EVIDENCE",
    "SIMILARITY_BOUNDARY",
    "SOURCE_LEAKAGE",
    "RIGHTS_POSTURE",
    "SECURITY_BOUNDARY",
    "SYNTHETIC_TESTS",
)
_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_REVISION = re.compile(r"\A[0-9a-f]{7,64}\Z")
_NONCE = re.compile(r"\A[0-9a-f-]{36}\Z")


def _canonical(value: object) -> bytes:
    def default(item: object) -> object:
        if isinstance(item, datetime):
            if item.tzinfo is None:
                raise AnalogReviewError("NAIVE_TIMESTAMP")
            return item.astimezone(UTC).isoformat(timespec="microseconds")
        if isinstance(item, StrEnum):
            return item.value
        raise TypeError(type(item).__name__)

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=default).encode()


def _digest(value: object) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class ReviewPacket:
    request_fingerprint: str
    campaign_id: str
    candidate_name: str
    manifest_digest: str
    content_digest: str
    lineage_digest: str
    policy_version: str
    revision: str
    checks: tuple[tuple[str, bool], ...]

    @property
    def fingerprint(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True)
class SignedReviewDecision:
    request_fingerprint: str
    packet_fingerprint: str
    candidate_name: str
    content_digest: str
    lineage_digest: str
    policy_version: str
    revision: str
    verdict: ReviewVerdict
    expires_at: datetime
    nonce: str
    signature: str = ""


@dataclass(frozen=True)
class AcceptedReview:
    candidate_name: str
    outcome: ReviewOutcome
    packet_fingerprint: str
    decision_digest: str
    owned_asset: bool = False
    intent_dna_mutation_allowed: bool = False
    mjn_write_allowed: bool = False


class AnalogReviewPacketBuilder:
    """Produces deterministic evidence packets; it cannot decide or sign reviews."""

    @staticmethod
    def build(
        manifest_payload: bytes, *, policy_version: str, revision: str
    ) -> tuple[ReviewPacket, ...]:
        result = validate_analog_manifest(manifest_payload)
        if not policy_version or not _REVISION.fullmatch(revision):
            raise AnalogReviewError("INVALID_REVIEW_BINDING")
        try:
            document = json.loads(manifest_payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:  # defensive after validation
            raise AnalogReviewError("INVALID_MANIFEST") from exc
        manifest_digest = "sha256:" + sha256(manifest_payload).hexdigest()
        request_fingerprint = _digest(
            {
                "campaign_id": result.campaign_id,
                "manifest_digest": manifest_digest,
                "policy_version": policy_version,
                "revision": revision,
            }
        )
        source_by_ref = {item["evidence_ref"]: item for item in document["sources"]}
        packets: list[ReviewPacket] = []
        for candidate in document["candidates"]:
            candidate_content = {
                key: value
                for key, value in candidate.items()
                if key not in {"external_evidence_refs", "mjn_evidence_refs"}
            }
            lineages = sorted(
                {source_by_ref[ref]["lineage"] for ref in candidate["external_evidence_refs"]}
            )
            evidence = {
                "external": sorted(candidate["external_evidence_refs"]),
                "mjn": sorted(candidate["mjn_evidence_refs"]),
                "lineages": lineages,
            }
            checks = tuple((name, True) for name in REQUIRED_CHECKS)
            packets.append(
                ReviewPacket(
                    request_fingerprint=request_fingerprint,
                    campaign_id=result.campaign_id,
                    candidate_name=candidate["name"],
                    manifest_digest=manifest_digest,
                    content_digest=_digest(candidate_content),
                    lineage_digest=_digest(evidence),
                    policy_version=policy_version,
                    revision=revision,
                    checks=checks,
                )
            )
        return tuple(packets)


def _decision_payload(decision: SignedReviewDecision) -> bytes:
    value = asdict(replace(decision, signature=""))
    return _canonical(value)


class EthernianReviewSigner:
    """Offline Ethernian helper. Never provide this private-key holder to ARKAON."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key

    def sign(
        self,
        packet: ReviewPacket,
        *,
        verdict: ReviewVerdict,
        expires_at: datetime,
        nonce: str,
    ) -> SignedReviewDecision:
        decision = SignedReviewDecision(
            request_fingerprint=packet.request_fingerprint,
            packet_fingerprint=packet.fingerprint,
            candidate_name=packet.candidate_name,
            content_digest=packet.content_digest,
            lineage_digest=packet.lineage_digest,
            policy_version=packet.policy_version,
            revision=packet.revision,
            verdict=verdict,
            expires_at=expires_at,
            nonce=nonce,
        )
        return replace(decision, signature=self._key.sign(_decision_payload(decision)).hex())


class AnalogReviewEvaluator:
    """ARKAON-side verifier: public-key verification only, with fail-closed replay rules."""

    def __init__(
        self,
        public_key: Ed25519PublicKey,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._key = public_key
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._used_nonces: set[str] = set()

    def accept(self, packet: ReviewPacket, decision: SignedReviewDecision) -> AcceptedReview:
        now = self._now()
        if now.tzinfo is None:
            raise AnalogReviewError("NAIVE_CLOCK")
        if tuple(name for name, passed in packet.checks) != REQUIRED_CHECKS or not all(
            passed for _, passed in packet.checks
        ):
            raise AnalogReviewError("REVIEW_PACKET_CHECK_FAILED")
        bindings = (
            decision.request_fingerprint == packet.request_fingerprint,
            decision.packet_fingerprint == packet.fingerprint,
            decision.candidate_name == packet.candidate_name,
            decision.content_digest == packet.content_digest,
            decision.lineage_digest == packet.lineage_digest,
            decision.policy_version == packet.policy_version,
            decision.revision == packet.revision,
        )
        if not all(bindings):
            raise AnalogReviewError("REVIEW_BINDING_MISMATCH")
        if not _NONCE.fullmatch(decision.nonce) or decision.nonce in self._used_nonces:
            raise AnalogReviewError("REVIEW_REPLAY_BLOCKED")
        if decision.expires_at.tzinfo is None or now >= decision.expires_at:
            raise AnalogReviewError("REVIEW_DECISION_EXPIRED")
        if not isinstance(decision.verdict, ReviewVerdict):
            raise AnalogReviewError("INVALID_REVIEW_VERDICT")
        try:
            self._key.verify(bytes.fromhex(decision.signature), _decision_payload(decision))
        except (InvalidSignature, ValueError, TypeError):
            raise AnalogReviewError("INVALID_ETHERNIAN_SIGNATURE") from None
        self._used_nonces.add(decision.nonce)
        outcomes = {
            ReviewVerdict.APPROVE: ReviewOutcome.APPROVED_FOR_PATTERN_PROMOTION,
            ReviewVerdict.REVIEW: ReviewOutcome.ETHERNIAN_REVIEW_REQUIRED,
            ReviewVerdict.DENY: ReviewOutcome.DENIED,
        }
        return AcceptedReview(
            candidate_name=packet.candidate_name,
            outcome=outcomes[decision.verdict],
            packet_fingerprint=packet.fingerprint,
            decision_digest=_digest(asdict(decision)),
        )
