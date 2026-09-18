"""Fail-closed ARKAON capability limits derived from collected evidence quality."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvidenceKind(StrEnum):
    FIRST_PARTY_AUTHORIZED = "FIRST_PARTY_AUTHORIZED"
    OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCUMENTATION"
    LICENSED_OPEN_SOURCE = "LICENSED_OPEN_SOURCE"
    PUBLIC_SNS = "PUBLIC_SNS"
    PUBLIC_SHORTFORM = "PUBLIC_SHORTFORM"
    UNKNOWN = "UNKNOWN"


class CapabilityTier(StrEnum):
    QUARANTINE = "QUARANTINE"
    ANALYZE_ONLY = "ANALYZE_ONLY"
    PROPOSE_ONLY = "PROPOSE_ONLY"
    REVIEW_ELIGIBLE = "REVIEW_ELIGIBLE"


_TIER_CAPABILITIES: dict[CapabilityTier, frozenset[str]] = {
    CapabilityTier.QUARANTINE: frozenset(),
    CapabilityTier.ANALYZE_ONLY: frozenset({"READ", "ANALYZE", "WARN"}),
    CapabilityTier.PROPOSE_ONLY: frozenset(
        {
            "READ",
            "ANALYZE",
            "WARN",
            "ABSTRACT_PATTERN",
            "DESIGN_IMPROVEMENT",
            "BUILD_SANDBOX_CANDIDATE",
            "RUN_SYNTHETIC_TESTS",
            "PROPOSE",
        }
    ),
    CapabilityTier.REVIEW_ELIGIBLE: frozenset(
        {
            "READ",
            "ANALYZE",
            "WARN",
            "ABSTRACT_PATTERN",
            "DESIGN_IMPROVEMENT",
            "BUILD_SANDBOX_CANDIDATE",
            "RUN_SYNTHETIC_TESTS",
            "PROPOSE",
            "REQUEST_REVIEW",
        }
    ),
}

_NEVER_GRANTED = frozenset(
    {
        "AUTHORIZE",
        "EXECUTE",
        "PUBLISH",
        "DEPLOY",
        "MERGE",
        "PAY",
        "SHARE_PERSONAL_DATA",
        "PROMOTE_OFFICIAL_PATTERN",
        "AUTOMATIC_LEARNING",
    }
)


@dataclass(frozen=True)
class CollectedEvidence:
    kind: EvidenceKind
    provenance_complete: bool
    authorization_valid: bool
    license_compatible: bool
    consent_valid: bool
    independently_verified: bool
    fresh: bool
    contains_sensitive_data: bool
    confidence_percent: int
    independent_source_count: int = 1

    def validate(self) -> None:
        if not isinstance(self.kind, EvidenceKind):
            raise TypeError("TYPED_EVIDENCE_KIND_REQUIRED")
        if type(self.confidence_percent) is not int or not 0 <= self.confidence_percent <= 100:
            raise ValueError("CONFIDENCE_PERCENT_REQUIRED")
        if type(self.independent_source_count) is not int or self.independent_source_count < 1:
            raise ValueError("INDEPENDENT_SOURCE_COUNT_REQUIRED")
        flags = (
            self.provenance_complete,
            self.authorization_valid,
            self.license_compatible,
            self.consent_valid,
            self.independently_verified,
            self.fresh,
            self.contains_sensitive_data,
        )
        if any(type(value) is not bool for value in flags):
            raise ValueError("STRICT_BOOLEAN_EVIDENCE_FLAGS_REQUIRED")


@dataclass(frozen=True)
class CapabilityDecision:
    tier: CapabilityTier
    allowed_capabilities: frozenset[str]
    denied_capabilities: frozenset[str]
    reason_codes: tuple[str, ...]

    def allows(self, capability: str) -> bool:
        return capability in self.allowed_capabilities


def limit_capabilities(evidence: CollectedEvidence) -> CapabilityDecision:
    if not isinstance(evidence, CollectedEvidence):
        raise TypeError("TYPED_COLLECTED_EVIDENCE_REQUIRED")
    evidence.validate()
    reasons: list[str] = []

    if evidence.contains_sensitive_data:
        tier = CapabilityTier.QUARANTINE
        reasons.append("SENSITIVE_DATA_QUARANTINE")
    elif not evidence.provenance_complete:
        tier = CapabilityTier.QUARANTINE
        reasons.append("PROVENANCE_INCOMPLETE")
    elif not evidence.authorization_valid or not evidence.license_compatible:
        tier = CapabilityTier.QUARANTINE
        reasons.append("RIGHTS_OR_LICENSE_INVALID")
    elif evidence.kind in {EvidenceKind.PUBLIC_SNS, EvidenceKind.PUBLIC_SHORTFORM}:
        if (
            evidence.consent_valid
            and evidence.fresh
            and evidence.independently_verified
            and evidence.confidence_percent >= 80
            and evidence.independent_source_count >= 2
        ):
            tier = CapabilityTier.PROPOSE_ONLY
            reasons.append("SOCIAL_INSIGHT_SANDBOX_IMPROVEMENT_ALLOWED")
        else:
            tier = CapabilityTier.ANALYZE_ONLY
            reasons.append("SOCIAL_MATERIAL_NEEDS_CORROBORATION")
    elif evidence.kind is EvidenceKind.UNKNOWN:
        tier = CapabilityTier.ANALYZE_ONLY
        reasons.append("UNKNOWN_SOURCE_ANALYSIS_ONLY")
    elif not evidence.consent_valid:
        tier = CapabilityTier.ANALYZE_ONLY
        reasons.append("CONSENT_NOT_VERIFIED")
    elif not evidence.fresh or evidence.confidence_percent < 70:
        tier = CapabilityTier.ANALYZE_ONLY
        reasons.append("STALE_OR_LOW_CONFIDENCE")
    elif not evidence.independently_verified or evidence.confidence_percent < 90:
        tier = CapabilityTier.PROPOSE_ONLY
        reasons.append("INDEPENDENT_REVIEW_REQUIRED")
    else:
        tier = CapabilityTier.REVIEW_ELIGIBLE
        reasons.append("EVIDENCE_READY_FOR_HUMAN_REVIEW")

    allowed = _TIER_CAPABILITIES[tier]
    return CapabilityDecision(
        tier=tier,
        allowed_capabilities=allowed,
        denied_capabilities=_NEVER_GRANTED | (set().union(*_TIER_CAPABILITIES.values()) - allowed),
        reason_codes=tuple(reasons),
    )
