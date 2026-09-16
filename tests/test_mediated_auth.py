from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.mediated_auth import (
    AttestationSigner,
    AuthGateError,
    AuthMethod,
    AuthRequest,
    AuthState,
    MediatedAuthAcquisition,
    OpaqueGrant,
)

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def request(**overrides):
    values = {
        "service_origin": "https://docs.example.test",
        "purpose": "read licensed metadata",
        "scopes": ("docs.read",),
        "read_only": True,
        "expected_asset_types": ("architecture-metadata",),
        "public_source_gap": "public index omits licensed metadata",
        "terms_and_license": "contract permits internal derivation",
        "risks": ("restricted source",),
        "expires_at": NOW + timedelta(minutes=10),
        "auth_method": AuthMethod.BROWSER_AUTH,
    }
    values.update(overrides)
    return AuthRequest(**values)


@pytest.fixture
def authorities():
    return Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()


def gate(req, authorities, now=NOW):
    return MediatedAuthAcquisition(
        req,
        ethernian_public_key=authorities[0].public_key(),
        mediator_public_key=authorities[1].public_key(),
        now_provider=lambda: now,
    )


def preflight(req, key, **overrides):
    values = {
        "request": req,
        "expires_at": NOW + timedelta(minutes=5),
        "nonce": str(uuid4()),
        "official_domain": True,
        "auth_method_allowlisted": True,
        "scopes_minimal": True,
        "source_authorized": True,
        "robots_terms_license_ok": True,
        "assetization_possible": True,
        "privacy_secret_boundary_ok": True,
    }
    values.update(overrides)
    return AttestationSigner(key).sign_preflight(**values)


def grant(req, **overrides):
    values = {
        "reference": f"grantref:{uuid4()}",
        "audience": req.service_origin,
        "scopes": req.scopes,
        "purpose": req.purpose,
        "expires_at": NOW + timedelta(minutes=5),
    }
    values.update(overrides)
    return OpaqueGrant(**values)


def prepared(req, authorities):
    result = gate(req, authorities)
    result.preflight(preflight(req, authorities[0]))
    result.await_user_auth()
    return result


def test_complete_flow_stops_at_ready_to_report(authorities):
    req = request()
    result = prepared(req, authorities)
    result.accept_grant(grant(req))
    result.collect(provenance="official export", license_id="internal", content=b"x")
    result.begin_asset_review()
    result.approve_for_report(provenance_ok=True, license_ok=True, content_hash_ok=True)
    assert result.state == AuthState.READY_TO_REPORT
    assert result.audit_codes[-1] == "READY_TO_REPORT_NOT_OWNED_ASSET"


@pytest.mark.parametrize(
    "origin",
    [
        "http://docs.example.test",
        "https://u:x@docs.example.test",
        "https://docs.example.test/path",
        "https://docs.example.test:bad",
    ],
)
def test_request_requires_canonical_secure_origin(origin):
    with pytest.raises(AuthGateError, match="NON_CANONICAL_ORIGIN"):
        request(service_origin=origin)


def test_fingerprint_is_canonical_and_change_sensitive():
    req = request(correlation_id=uuid4())
    assert req.fingerprint == request(correlation_id=req.correlation_id).fingerprint
    assert (
        req.fingerprint != request(correlation_id=req.correlation_id, scopes=("other",)).fingerprint
    )


@pytest.mark.parametrize(
    "field",
    [
        "official_domain",
        "auth_method_allowlisted",
        "scopes_minimal",
        "source_authorized",
        "robots_terms_license_ok",
        "assetization_possible",
        "privacy_secret_boundary_ok",
    ],
)
def test_each_signed_false_preflight_fails_closed(authorities, field):
    req = request()
    with pytest.raises(AuthGateError, match="ETHERNIAN_PREFLIGHT_DENIED"):
        gate(req, authorities).preflight(preflight(req, authorities[0], **{field: False}))


def test_preflight_rejects_tamper_wrong_request_wrong_key_and_expiry(authorities):
    req = request()
    signed = preflight(req, authorities[0])
    with pytest.raises(AuthGateError, match="INVALID_ATTESTATION_SIGNATURE"):
        gate(req, authorities).preflight(replace(signed, scopes_minimal=False))
    with pytest.raises(AuthGateError, match="ETHERNIAN_PREFLIGHT_DENIED"):
        gate(req, authorities).preflight(preflight(request(), authorities[0]))
    with pytest.raises(AuthGateError, match="INVALID_ATTESTATION_SIGNATURE"):
        gate(req, authorities).preflight(preflight(req, Ed25519PrivateKey.generate()))
    with pytest.raises(AuthGateError, match="ATTESTATION_EXPIRED"):
        gate(req, authorities).preflight(preflight(req, authorities[0], expires_at=NOW))


def test_preflight_nonce_replay_is_blocked(authorities):
    req = request()
    result, signed = gate(req, authorities), preflight(req, authorities[0])
    result.preflight(signed)
    result.state = AuthState.REQUESTED
    with pytest.raises(AuthGateError, match="ATTESTATION_REPLAY_BLOCKED"):
        result.preflight(signed)


def user_attestation(req, item, key, **overrides):
    values = {
        "request": req,
        "actions": req.user_actions,
        "grant_reference": item.reference,
        "expires_at": NOW + timedelta(minutes=4),
        "nonce": str(uuid4()),
    }
    values.update(overrides)
    return AttestationSigner(key).sign_user_actions(**values)


def test_sensitive_actions_require_exact_mediator_attestation(authorities):
    req = request(user_actions=("MFA", "paid purchase"))
    result, item = prepared(req, authorities), grant(req)
    with pytest.raises(AuthGateError, match="USER_ACTION_ATTESTATION_REQUIRED"):
        result.accept_grant(item)
    result.accept_grant(item, user_action_attestation=user_attestation(req, item, authorities[1]))
    assert result.state == AuthState.GRANTED


@pytest.mark.parametrize("mutation", ["actions", "grant", "request"])
def test_user_action_attestation_rejects_wrong_binding(authorities, mutation):
    req = request(user_actions=("CAPTCHA",))
    result, item = prepared(req, authorities), grant(req)
    signed = user_attestation(
        request() if mutation == "request" else req,
        item,
        authorities[1],
        actions=("consent",) if mutation == "actions" else req.user_actions,
        grant_reference=f"grantref:{uuid4()}" if mutation == "grant" else item.reference,
    )
    with pytest.raises(AuthGateError, match="USER_ACTION_ATTESTATION_MISMATCH"):
        result.accept_grant(item, user_action_attestation=signed)


def test_user_action_wrong_signer_and_tamper_are_rejected(authorities):
    req = request(user_actions=("consent",))
    item = grant(req)
    wrong = user_attestation(req, item, Ed25519PrivateKey.generate())
    with pytest.raises(AuthGateError, match="INVALID_ATTESTATION_SIGNATURE"):
        prepared(req, authorities).accept_grant(item, user_action_attestation=wrong)
    signed = user_attestation(req, item, authorities[1])
    with pytest.raises(AuthGateError, match="INVALID_ATTESTATION_SIGNATURE"):
        prepared(req, authorities).accept_grant(
            item, user_action_attestation=replace(signed, actions=("MFA",))
        )


def test_clock_controls_attestation_and_grant_expiry(authorities):
    req = request()
    with pytest.raises(AuthGateError, match="ATTESTATION_EXPIRED"):
        gate(req, authorities, NOW + timedelta(minutes=6)).preflight(preflight(req, authorities[0]))
    result = prepared(req, authorities)
    with pytest.raises(AuthGateError, match="GRANT_BINDING_MISMATCH"):
        result.accept_grant(grant(req, expires_at=NOW))


@pytest.mark.parametrize(
    "value",
    ["password: correct-horse-battery-staple", "api_key=abcdefghijklmnop", "person@example.com"],
)
def test_secret_or_pii_never_enters_request(value):
    with pytest.raises(AuthGateError, match="SECRET_OR_PII_BLOCKED"):
        request(public_source_gap=value)


def test_raw_credential_cannot_masquerade_as_grant_reference():
    with pytest.raises(AuthGateError, match="GRANT_REFERENCE_NOT_OPAQUE"):
        grant(request(), reference="password: correct-horse-battery-staple")


def test_single_use_grant_replay_is_blocked(authorities):
    req = request()
    result = prepared(req, authorities)
    result.accept_grant(grant(req))
    result.collect(provenance="official", license_id="internal", content=b"x")
    with pytest.raises(AuthGateError, match="GRANT_REPLAY_BLOCKED"):
        result.collect(provenance="official", license_id="internal", content=b"x")
