from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.authorized_material import (
    AuthorizedMaterialPipeline,
    CaptureBundle,
    CollectionPosture,
    EthernianSigner,
    ImprovementEvidence,
    LicenseTerms,
    MaterialError,
    MaterialRequest,
    MaterialState,
    ReviewDecision,
    RightsEvidence,
    SourceRights,
    UseRoute,
    originality_payload_fingerprint,
)

NOW = datetime(2026, 9, 15, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def terms(**overrides: object) -> LicenseTerms:
    values = {
        "identifier": "MIT",
        "allow_use": True,
        "allow_modify": True,
        "allow_redistribute": True,
    }
    values.update(overrides)
    return LicenseTerms(**values)  # type: ignore[arg-type]


def evidence(
    rights: SourceRights = SourceRights.PERMISSIVE_LICENSE, **kw: object
) -> RightsEvidence:
    return RightsEvidence(rights, HASH, kw.get("license_terms", terms()), "licensor")  # type: ignore[arg-type]


def request(route: UseRoute = UseRoute.LICENSED_REUSE, **kw: object) -> MaterialRequest:
    values = {
        "source_url": "https://example.test/app.js",
        "allowed_origins": ("https://example.test",),
        "route": route,
        "purpose": "authorized pattern study",
        "allowed_content_types": ("application/javascript", "text/css", "text/html"),
        "max_requests": 3,
        "max_bytes": 20_000,
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(kw)
    return MaterialRequest(**values)  # type: ignore[arg-type]


def pipeline(req: MaterialRequest, *, private: Ed25519PrivateKey | None = None):
    key = private or Ed25519PrivateKey.generate()
    return AuthorizedMaterialPipeline(
        req, ethernian_public_key=key.public_key(), now_provider=lambda: NOW
    ), EthernianSigner(key)


def attest(
    signer: EthernianSigner,
    req: MaterialRequest,
    rights: RightsEvidence,
    stage="RIGHTS",
    decision=ReviewDecision.APPROVE,
    nonce="00000000-0000-0000-0000-000000000001",
    payload=None,
):
    return signer.sign(
        req,
        rights,
        stage=stage,
        stage_payload_fingerprint=payload or rights.fingerprint,
        decision=decision,
        expires_at=NOW + timedelta(minutes=10),
        nonce=nonce,
    )


def evaluated(
    route=UseRoute.LICENSED_REUSE, rights=SourceRights.PERMISSIVE_LICENSE, license_terms=None
):
    req, ev = request(route), evidence(rights, license_terms=license_terms or terms())
    gate, signer = pipeline(req)
    gate.evaluate_rights(ev, attest(signer, req, ev))
    return gate, signer, req, ev


def pass_policy(gate, signer, req, ev, posture=None):
    posture = posture or CollectionPosture("ALLOW", "OK")
    gate.pass_collection_policy(
        posture,
        attestation=attest(
            signer,
            req,
            ev,
            "COLLECTION_POLICY",
            nonce="00000000-0000-0000-0000-000000000020",
            payload=posture.fingerprint,
        ),
    )


def improvement(dimension="STRUCTURE", before="old", after="new"):
    return ImprovementEvidence(dimension, "sha256:" + "b" * 64, before, after)


def originality_attestation(
    signer, req, ev, content, improvements=(), nonce="00000000-0000-0000-0000-000000000002"
):
    payload = originality_payload_fingerprint(
        candidate_content=content, route=req.route, evidence=improvements
    )
    return attest(signer, req, ev, "ORIGINALITY", nonce=nonce, payload=payload)


@pytest.mark.parametrize(
    "right",
    [
        SourceRights.USER_OWNED,
        SourceRights.EXPLICIT_PERMISSION,
        SourceRights.PERMISSIVE_LICENSE,
        SourceRights.ATTRIBUTION_LICENSE,
        SourceRights.COPYLEFT_LICENSE,
    ],
)
def test_authorized_rights_allow_licensed_reuse(right):
    license_terms = terms(
        attribution_required=right is SourceRights.ATTRIBUTION_LICENSE,
        source_disclosure_required=right is SourceRights.COPYLEFT_LICENSE,
    )
    gate, _, _, _ = evaluated(rights=right, license_terms=license_terms)
    assert gate.state is MaterialState.RIGHTS_EVALUATED


def test_declared_license_class_requires_its_obligation():
    with pytest.raises(MaterialError, match="ATTRIBUTION_OBLIGATION_MISSING"):
        evidence(SourceRights.ATTRIBUTION_LICENSE)
    with pytest.raises(MaterialError, match="COPYLEFT_OBLIGATION_MISSING"):
        evidence(SourceRights.COPYLEFT_LICENSE)


def test_attribution_and_copyleft_obligations_are_preserved():
    license_terms = terms(attribution_required=True, source_disclosure_required=True)
    gate, signer, req, ev = evaluated(license_terms=license_terms)
    pass_policy(gate, signer, req, ev)
    gate.capture(CaptureBundle(req.source_url, "text/css", ".a{color:red}"))
    gate.sanitize()
    gate.normalize()
    gate.begin_originality_review()
    candidate = gate.approve_candidate(
        ".ours{color:blue}",
        improvement_evidence=(),
        attestation=originality_attestation(signer, req, ev, ".ours{color:blue}"),
    )
    assert candidate.obligations == ("ATTRIBUTION", "SOURCE_DISCLOSURE")
    assert candidate.status == "CANDIDATE_NOT_OWNED_ASSET"


def test_public_observation_reuse_and_unknown_require_review():
    for right in (SourceRights.PUBLIC_OBSERVATION, SourceRights.UNKNOWN):
        req, ev = request(), evidence(right)
        gate, signer = pipeline(req)
        gate.evaluate_rights(ev, attest(signer, req, ev))
        assert gate.state is MaterialState.ETHERNIAN_REVIEW


def test_public_observation_adaptive_route_is_allowed():
    gate, _, _, _ = evaluated(UseRoute.ADAPTIVE_REIMPLEMENTATION, SourceRights.PUBLIC_OBSERVATION)
    assert gate.state is MaterialState.RIGHTS_EVALUATED


def test_license_permission_is_machine_enforced():
    req, ev = request(), evidence(license_terms=terms(allow_modify=False))
    gate, signer = pipeline(req)
    with pytest.raises(MaterialError, match="LICENSE_ROUTE_NOT_ALLOWED"):
        gate.evaluate_rights(ev, attest(signer, req, ev))


def test_robots_conflict_routes_to_review_but_direct_permission_can_override():
    gate, signer, req, ev = evaluated()
    pass_policy(gate, signer, req, ev, CollectionPosture("DISALLOW", "OK"))
    assert gate.state is MaterialState.ETHERNIAN_REVIEW
    gate, signer, req, ev = evaluated(rights=SourceRights.EXPLICIT_PERMISSION)
    pass_policy(gate, signer, req, ev, CollectionPosture("DISALLOW", "CONFLICT", True))
    assert gate.state is MaterialState.COLLECTION_POLICY_PASSED


def test_unknown_posture_needs_review_and_unauthorized_access_is_denied():
    gate, signer, req, ev = evaluated()
    pass_policy(gate, signer, req, ev, CollectionPosture("UNKNOWN", "OK"))
    assert gate.state is MaterialState.ETHERNIAN_REVIEW

    gate, signer, req, ev = evaluated()
    posture = CollectionPosture("ALLOW", "OK", access_authorized=False)
    with pytest.raises(MaterialError, match="UNAUTHORIZED_ACCESS_DENIED"):
        pass_policy(gate, signer, req, ev, posture)
    assert gate.state is MaterialState.DENIED


def test_redirect_escape_is_denied():
    gate, signer, req, ev = evaluated()
    pass_policy(gate, signer, req, ev)
    with pytest.raises(MaterialError, match="REDIRECT_ORIGIN_BLOCKED"):
        gate.validate_redirect("https://evil.test/payload")


def test_har_dom_and_query_secrets_and_pii_are_redacted():
    gate, signer, req, ev = evaluated()
    pass_policy(gate, signer, req, ev)
    gate.capture(
        CaptureBundle(
            req.source_url + "?token=abc&view=ok",
            "text/html",
            "mail me at a@b.com",
            har={
                "headers": {"Authorization": "Bearer abcdefghijklmnop", "Accept": "text/html"},
                "url": "https://example.test/x?api_key=secret",
            },
            dom="<p>010-1234-5678</p>",
        )
    )
    clean = gate.sanitize()
    assert "abc" not in clean.url and "a@b.com" not in clean.body
    assert clean.har["headers"]["Authorization"] == "[REDACTED]"  # type: ignore[index]
    assert "010-1234-5678" not in clean.dom


def test_public_sourcemap_requires_authorization():
    gate, signer, req, ev = evaluated(
        UseRoute.ADAPTIVE_REIMPLEMENTATION, SourceRights.PUBLIC_OBSERVATION
    )
    pass_policy(gate, signer, req, ev)
    with pytest.raises(MaterialError, match="SOURCEMAP_AUTHORIZATION_REQUIRED"):
        gate.capture(
            CaptureBundle(req.source_url, "application/javascript", "x()", source_map="{}")
        )


def test_static_obfuscated_js_normalization_is_identifier_independent():
    gate, signer, req, ev = evaluated()
    pass_policy(gate, signer, req, ev)
    gate.capture(
        CaptureBundle(
            req.source_url, "application/javascript", "const _0xabc=(x)=>{if(x)return x+1};"
        )
    )
    gate.sanitize()
    normalized = gate.normalize()
    assert "_0xabc" not in normalized.normalized
    assert normalized.language == "javascript"
    assert "branches:1" in normalized.structural_summary


@pytest.mark.parametrize(
    "flag", ["attempts_to_bypass_access_control", "requests_private_or_secret_material"]
)
def test_circumvention_and_private_material_are_denied(flag):
    req = request(**{flag: True})
    ev, key = evidence(), Ed25519PrivateKey.generate()
    gate, signer = pipeline(req, private=key)
    with pytest.raises(MaterialError, match="PROHIBITED_ACQUISITION"):
        gate.evaluate_rights(ev, attest(signer, req, ev))
    assert gate.state is MaterialState.DENIED


def test_adaptation_needs_material_improvement_and_blocks_large_fragment():
    gate, signer, req, ev = evaluated(UseRoute.ADAPTIVE_REIMPLEMENTATION)
    pass_policy(gate, signer, req, ev)
    source = "function original(){return '" + "x" * 180 + "';}"
    gate.capture(CaptureBundle(req.source_url, "application/javascript", source))
    gate.sanitize()
    gate.normalize()
    gate.begin_originality_review()
    att = originality_attestation(signer, req, ev, "renamed")
    with pytest.raises(MaterialError, match="NO_MATERIAL_IMPROVEMENT"):
        gate.approve_candidate("renamed", improvement_evidence=(), attestation=att)
    # Invalid improvement does not consume a valid signed approval beyond cryptographic verification.
    changes = (improvement(),)
    att2 = originality_attestation(
        signer, req, ev, source, changes, "00000000-0000-0000-0000-000000000003"
    )
    with pytest.raises(MaterialError, match="LARGE_SOURCE_FRAGMENT_LEAK"):
        gate.approve_candidate(source, improvement_evidence=changes, attestation=att2)
    assert gate.state is MaterialState.QUARANTINED


def test_attestation_tamper_wrong_key_replay_and_expiry_are_blocked():
    req, ev = request(), evidence()
    gate, signer = pipeline(req)
    valid = attest(signer, req, ev)
    with pytest.raises(MaterialError, match="INVALID_ATTESTATION_SIGNATURE"):
        gate.evaluate_rights(ev, replace(valid, decision=ReviewDecision.DENY))

    wrong_gate, _wrong_signer = pipeline(req)
    with pytest.raises(MaterialError, match="INVALID_ATTESTATION_SIGNATURE"):
        wrong_gate.evaluate_rights(ev, attest(signer, req, ev))

    expiry_key = Ed25519PrivateKey.generate()
    expiry_signer = EthernianSigner(expiry_key)
    expired = expiry_signer.sign(
        req,
        ev,
        stage="RIGHTS",
        stage_payload_fingerprint=ev.fingerprint,
        decision=ReviewDecision.APPROVE,
        expires_at=NOW,
        nonce="00000000-0000-0000-0000-000000000009",
    )
    fresh_gate, _ = pipeline(req, private=expiry_key)
    with pytest.raises(MaterialError, match="ATTESTATION_EXPIRED"):
        fresh_gate.evaluate_rights(ev, expired)

    replay_gate, replay_signer = pipeline(req)
    signed = attest(replay_signer, req, ev)
    replay_gate._verify(signed, stage="RIGHTS", rights=ev, stage_payload_fingerprint=ev.fingerprint)
    with pytest.raises(MaterialError, match="ATTESTATION_REPLAY_BLOCKED"):
        replay_gate._verify(
            signed, stage="RIGHTS", rights=ev, stage_payload_fingerprint=ev.fingerprint
        )


def test_request_fingerprint_binds_all_parameters():
    assert request().fingerprint != request(max_bytes=20_001).fingerprint


def test_request_url_cannot_persist_query_credentials():
    with pytest.raises(MaterialError, match="REQUEST_URL_SECRET_BLOCKED"):
        request(source_url="https://example.test/app.js?access_token=topsecret")


def test_attestation_for_another_request_is_rejected():
    req, other, ev = request(), request(max_bytes=20_001), evidence()
    gate, signer = pipeline(req)
    with pytest.raises(MaterialError, match="ATTESTATION_BINDING_MISMATCH"):
        gate.evaluate_rights(ev, attest(signer, other, ev))


def test_adaptive_candidate_blocks_source_identifier_and_personal_data():
    gate, signer, req, ev = evaluated(UseRoute.ADAPTIVE_REIMPLEMENTATION)
    pass_policy(gate, signer, req, ev)
    gate.capture(
        CaptureBundle(
            req.source_url,
            "application/javascript",
            "function vendorSpecificCheckoutFlow(){return true}",
        )
    )
    gate.sanitize()
    gate.normalize()
    gate.begin_originality_review()
    changes = (improvement("SAFETY"),)
    leaked = "function vendorSpecificCheckoutFlow(){return false}"
    signed = originality_attestation(
        signer, req, ev, leaked, changes, "00000000-0000-0000-0000-000000000011"
    )
    with pytest.raises(MaterialError, match="SOURCE_IDENTIFIER_LEAK"):
        gate.approve_candidate(
            leaked,
            improvement_evidence=changes,
            attestation=signed,
        )

    # A fresh workflow also quarantines personal data in a generated candidate.
    gate, signer, req, ev = evaluated(UseRoute.ADAPTIVE_REIMPLEMENTATION)
    pass_policy(gate, signer, req, ev)
    gate.capture(CaptureBundle(req.source_url, "application/javascript", "const safe=1"))
    gate.sanitize()
    gate.normalize()
    gate.begin_originality_review()
    changes = (improvement("USABILITY"),)
    pii_candidate = "support='person@example.com'"
    signed = originality_attestation(
        signer, req, ev, pii_candidate, changes, "00000000-0000-0000-0000-000000000012"
    )
    with pytest.raises(MaterialError, match="CANDIDATE_SECRET_OR_PII_BLOCKED"):
        gate.approve_candidate(
            pii_candidate,
            improvement_evidence=changes,
            attestation=signed,
        )


def test_collection_budgets_and_content_type_are_enforced():
    req = request(max_bytes=2)
    ev = evidence()
    gate, signer = pipeline(req)
    gate.evaluate_rights(ev, attest(signer, req, ev))
    pass_policy(gate, signer, req, ev)
    with pytest.raises(MaterialError, match="COLLECTION_BUDGET_EXCEEDED"):
        gate.capture(CaptureBundle(req.source_url, "text/css", "abc"))


def test_collection_policy_attestation_blocks_tamper_replay_wrong_request_key_and_expiry():
    req, ev = request(), evidence()
    shared_key = Ed25519PrivateKey.generate()
    gate, signer = pipeline(req, private=shared_key)
    gate.evaluate_rights(ev, attest(signer, req, ev))
    posture = CollectionPosture("ALLOW", "OK")
    signed = attest(
        signer,
        req,
        ev,
        "COLLECTION_POLICY",
        payload=posture.fingerprint,
        nonce="00000000-0000-0000-0000-000000000030",
    )
    with pytest.raises(MaterialError, match="ATTESTATION_PAYLOAD_MISMATCH"):
        gate.pass_collection_policy(CollectionPosture("DISALLOW", "OK"), attestation=signed)

    gate.pass_collection_policy(posture, attestation=signed)
    with pytest.raises(MaterialError, match="ATTESTATION_REPLAY_BLOCKED"):
        gate._verify(
            signed,
            stage="COLLECTION_POLICY",
            rights=ev,
            stage_payload_fingerprint=posture.fingerprint,
        )

    other = request(max_bytes=20_001)
    other_gate, _ = pipeline(other, private=shared_key)
    other_gate.evaluate_rights(ev, attest(signer, other, ev))
    with pytest.raises(MaterialError, match="ATTESTATION_BINDING_MISMATCH"):
        other_gate.pass_collection_policy(posture, attestation=signed)

    wrong_gate, wrong_signer = pipeline(req)
    wrong_gate.evaluate_rights(ev, attest(wrong_signer, req, ev))
    with pytest.raises(MaterialError, match="INVALID_ATTESTATION_SIGNATURE"):
        wrong_gate.pass_collection_policy(posture, attestation=signed)

    expiry_key = Ed25519PrivateKey.generate()
    expiry_gate, expiry_signer = pipeline(req, private=expiry_key)
    expiry_gate.evaluate_rights(ev, attest(expiry_signer, req, ev))
    expired = expiry_signer.sign(
        req,
        ev,
        stage="COLLECTION_POLICY",
        stage_payload_fingerprint=posture.fingerprint,
        decision=ReviewDecision.APPROVE,
        expires_at=NOW,
        nonce="00000000-0000-0000-0000-000000000031",
    )
    with pytest.raises(MaterialError, match="ATTESTATION_EXPIRED"):
        expiry_gate.pass_collection_policy(posture, attestation=expired)


def _review_ready(route=UseRoute.ADAPTIVE_REIMPLEMENTATION):
    gate, signer, req, ev = evaluated(route)
    pass_policy(gate, signer, req, ev)
    gate.capture(CaptureBundle(req.source_url, "application/javascript", "const sourceValue=1"))
    gate.sanitize()
    gate.normalize()
    gate.begin_originality_review()
    return gate, signer, req, ev


def test_originality_attestation_binds_candidate_route_and_improvement_evidence():
    candidate = "const improved=2"
    changes = (improvement("PERFORMANCE", "20ms", "10ms"),)
    gate, signer, req, ev = _review_ready()
    signed = originality_attestation(signer, req, ev, candidate, changes)
    with pytest.raises(MaterialError, match="ATTESTATION_PAYLOAD_MISMATCH"):
        gate.approve_candidate(
            candidate + ";",
            improvement_evidence=changes,
            attestation=signed,
        )

    gate, signer, req, ev = _review_ready()
    signed = originality_attestation(signer, req, ev, candidate, changes)
    swapped = (improvement("SAFETY", "unsafe", "safe"),)
    with pytest.raises(MaterialError, match="ATTESTATION_PAYLOAD_MISMATCH"):
        gate.approve_candidate(candidate, improvement_evidence=swapped, attestation=signed)

    licensed_gate, _, _, _ = _review_ready(UseRoute.LICENSED_REUSE)
    with pytest.raises(MaterialError, match="ATTESTATION_BINDING_MISMATCH"):
        licensed_gate.approve_candidate(candidate, improvement_evidence=changes, attestation=signed)


def test_improvement_evidence_rejects_empty_fake_and_unchanged_claims():
    with pytest.raises(MaterialError, match="INVALID_IMPROVEMENT_DIMENSION"):
        improvement("COLOR")
    with pytest.raises(MaterialError, match="NO_MEASURABLE_OR_ASSESSED_IMPROVEMENT"):
        improvement("STRUCTURE", "same", "same")
    with pytest.raises(MaterialError, match="INVALID_IMPROVEMENT_EVIDENCE_HASH"):
        ImprovementEvidence("STRUCTURE", "not-a-digest", "old", "new")

    gate, signer, req, ev = _review_ready()
    candidate = "const improved=2"
    signed = originality_attestation(signer, req, ev, candidate, ())
    with pytest.raises(MaterialError, match="NO_MATERIAL_IMPROVEMENT"):
        gate.approve_candidate(candidate, improvement_evidence=(), attestation=signed)


def test_licensed_reuse_still_binds_approved_candidate_content_hash():
    gate, signer, req, ev = _review_ready(UseRoute.LICENSED_REUSE)
    approved = "const licensedCopy=1"
    signed = originality_attestation(signer, req, ev, approved)
    with pytest.raises(MaterialError, match="ATTESTATION_PAYLOAD_MISMATCH"):
        gate.approve_candidate("const substituted=2", improvement_evidence=(), attestation=signed)
