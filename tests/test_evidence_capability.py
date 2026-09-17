import pytest

from apf.evidence_capability import (
    CapabilityTier,
    CollectedEvidence,
    EvidenceKind,
    limit_capabilities,
)


def evidence(**changes) -> CollectedEvidence:
    values = {
        "kind": EvidenceKind.FIRST_PARTY_AUTHORIZED,
        "provenance_complete": True,
        "authorization_valid": True,
        "license_compatible": True,
        "consent_valid": True,
        "independently_verified": True,
        "fresh": True,
        "contains_sensitive_data": False,
        "confidence_percent": 95,
    }
    values.update(changes)
    return CollectedEvidence(**values)


def test_verified_evidence_can_only_reach_human_review() -> None:
    decision = limit_capabilities(evidence())
    assert decision.tier is CapabilityTier.REVIEW_ELIGIBLE
    assert decision.allows("REQUEST_REVIEW")
    for forbidden in ("AUTHORIZE", "EXECUTE", "PUBLISH", "DEPLOY", "MERGE", "PAY"):
        assert not decision.allows(forbidden)
        assert forbidden in decision.denied_capabilities


@pytest.mark.parametrize("kind", [EvidenceKind.PUBLIC_SNS, EvidenceKind.PUBLIC_SHORTFORM])
def test_social_and_shortform_material_remain_analysis_only(kind: EvidenceKind) -> None:
    decision = limit_capabilities(evidence(kind=kind))
    assert decision.tier is CapabilityTier.ANALYZE_ONLY
    assert decision.allowed_capabilities == frozenset({"READ", "ANALYZE", "WARN"})


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"contains_sensitive_data": True}, "SENSITIVE_DATA_QUARANTINE"),
        ({"provenance_complete": False}, "PROVENANCE_INCOMPLETE"),
        ({"authorization_valid": False}, "RIGHTS_OR_LICENSE_INVALID"),
        ({"license_compatible": False}, "RIGHTS_OR_LICENSE_INVALID"),
    ],
)
def test_unsafe_evidence_is_quarantined(changes, reason: str) -> None:
    decision = limit_capabilities(evidence(**changes))
    assert decision.tier is CapabilityTier.QUARANTINE
    assert decision.allowed_capabilities == frozenset()
    assert reason in decision.reason_codes


def test_unverified_evidence_cannot_become_review_eligible() -> None:
    decision = limit_capabilities(evidence(independently_verified=False))
    assert decision.tier is CapabilityTier.PROPOSE_ONLY
    assert not decision.allows("REQUEST_REVIEW")


def test_stale_or_low_confidence_evidence_is_analysis_only() -> None:
    assert limit_capabilities(evidence(fresh=False)).tier is CapabilityTier.ANALYZE_ONLY
    assert (
        limit_capabilities(evidence(confidence_percent=69)).tier
        is CapabilityTier.ANALYZE_ONLY
    )


def test_invalid_typed_fields_fail_closed() -> None:
    with pytest.raises(ValueError, match="CONFIDENCE_PERCENT_REQUIRED"):
        limit_capabilities(evidence(confidence_percent=True))
    with pytest.raises(ValueError, match="STRICT_BOOLEAN_EVIDENCE_FLAGS_REQUIRED"):
        limit_capabilities(evidence(fresh=1))
