import json
from hashlib import sha256
from uuid import uuid4

import pytest

from apf.billing_entitlement import (
    BillingEntitlementPolicy,
    BillingEntitlementRejected,
    BillingEntitlementVerifier,
    BillingVerificationMode,
    build_billing_verify_url,
    digest_entitlement,
    verify_billing_api_entitlement,
    verify_digest_entitlement,
)


def _policy(**overrides: object) -> BillingEntitlementPolicy:
    base = {
        "enabled": True,
        "mode": BillingVerificationMode.BILLING_API,
        "billing_api_base_url": "https://billing.example.test",
        "verify_path": "/v1/entitlements/verify",
        "api_token_env": "ARKAON_BILLING_API_TOKEN",
        "capability": "co_creation",
        "allow_digest_fallback": False,
    }
    base.update(overrides)
    return BillingEntitlementPolicy(**base)  # type: ignore[arg-type]


def test_verify_digest_entitlement():
    tenant = str(uuid4())
    principal = str(uuid4())
    platform = "NARANG_RIDER"
    digest = digest_entitlement(tenant_id=tenant, principal_id=principal, platform_id=platform)
    assert verify_digest_entitlement(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        digest=digest,
    )
    assert not verify_digest_entitlement(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        digest="a" * 64,
    )


def test_build_billing_verify_url_rejects_insecure_base():
    policy = _policy(billing_api_base_url="http://billing.example.test")
    with pytest.raises(BillingEntitlementRejected) as error:
        build_billing_verify_url(policy=policy)
    assert error.value.code == "BILLING_URL_INSECURE"


def test_verify_billing_api_entitlement_active(monkeypatch):
    tenant = str(uuid4())
    principal = str(uuid4())
    platform = "NARANG_RIDER"
    token = digest_entitlement(tenant_id=tenant, principal_id=principal, platform_id=platform)
    policy = _policy()
    monkeypatch.setenv("ARKAON_BILLING_API_TOKEN", "service-token")

    def fake_post(url, headers, body, timeout_seconds, max_response_bytes):
        assert url == "https://billing.example.test/v1/entitlements/verify"
        assert headers["Authorization"] == "Bearer service-token"
        payload = json.loads(body.decode())
        assert payload["tenant_id"] == tenant
        assert payload["principal_id"] == principal
        assert payload["platform_id"] == platform
        assert payload["entitlement_token"] == token
        assert payload["capability"] == "co_creation"
        return 200, json.dumps({"entitled": True, "status": "ACTIVE"}).encode()

    assert verify_billing_api_entitlement(
        policy=policy,
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        entitlement_token=token,
        http_post=fake_post,
    )


def test_verify_billing_api_entitlement_unpaid(monkeypatch):
    policy = _policy()
    monkeypatch.setenv("ARKAON_BILLING_API_TOKEN", "service-token")

    def fake_post(_url, _headers, _body, _timeout, _max_bytes):
        return 402, json.dumps({"entitled": False, "status": "UNPAID"}).encode()

    assert not verify_billing_api_entitlement(
        policy=policy,
        tenant_id=str(uuid4()),
        principal_id=str(uuid4()),
        platform_id="NARANG_RIDER",
        entitlement_token="b" * 64,
        http_post=fake_post,
    )


def test_verifier_digest_then_api_fallback(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-billing-entitlement.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.billing-entitlement/v1",
                "enabled": True,
                "mode": "DIGEST_THEN_API",
                "billing_api_base_url": "https://billing.example.test",
                "allow_digest_fallback": True,
            }
        ),
        encoding="utf-8",
    )
    tenant = str(uuid4())
    principal = str(uuid4())
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant}|{principal}|{platform}|paid".encode()).hexdigest()
    monkeypatch.delenv("ARKAON_BILLING_API_TOKEN", raising=False)

    def fake_post(_url, _headers, _body, _timeout, _max_bytes):
        return 503, b""

    verifier = BillingEntitlementVerifier(foundry_root=tmp_path, http_post=fake_post)
    assert verifier.verify(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        payment_entitlement_digest=digest,
    )


def test_verifier_billing_api_only_without_fallback(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-billing-entitlement.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.billing-entitlement/v1",
                "enabled": True,
                "mode": "BILLING_API",
                "billing_api_base_url": "https://billing.example.test",
                "allow_digest_fallback": False,
            }
        ),
        encoding="utf-8",
    )
    tenant = str(uuid4())
    principal = str(uuid4())
    platform = "NARANG_RIDER"
    digest = sha256(f"{tenant}|{principal}|{platform}|paid".encode()).hexdigest()
    monkeypatch.setenv("ARKAON_BILLING_API_TOKEN", "service-token")

    def fake_post(_url, _headers, _body, _timeout, _max_bytes):
        return 200, json.dumps({"entitled": False, "status": "UNPAID"}).encode()

    verifier = BillingEntitlementVerifier(foundry_root=tmp_path, http_post=fake_post)
    assert not verifier.verify(
        tenant_id=tenant,
        principal_id=principal,
        platform_id=platform,
        payment_entitlement_digest=digest,
    )


def test_policy_load_from_config(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    path = config / "arkaon-billing-entitlement.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "apf.billing-entitlement/v1",
                "mode": "BILLING_API",
                "billing_api_base_url": "https://billing.prod.example/",
                "verify_path": "/api/entitlements/verify",
                "api_token_env": "CUSTOM_BILLING_TOKEN",
                "capability": "co_creation",
            }
        ),
        encoding="utf-8",
    )
    policy = BillingEntitlementPolicy.load(path)
    assert policy.mode is BillingVerificationMode.BILLING_API
    assert build_billing_verify_url(policy=policy) == "https://billing.prod.example/api/entitlements/verify"
    assert policy.api_token_env == "CUSTOM_BILLING_TOKEN"
