"""Payment entitlement verification — digest prototype with billing API hook."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path


class BillingEntitlementRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BillingVerificationMode(str, Enum):
    DIGEST = "DIGEST"
    BILLING_API = "BILLING_API"
    DIGEST_THEN_API = "DIGEST_THEN_API"


@dataclass(frozen=True)
class BillingEntitlementPolicy:
    enabled: bool = True
    mode: BillingVerificationMode = BillingVerificationMode.DIGEST
    billing_api_base_url: str | None = None
    allow_digest_fallback: bool = True

    @classmethod
    def load(cls, path: Path) -> BillingEntitlementPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.billing-entitlement/v1":
            raise BillingEntitlementRejected("POLICY_SCHEMA", "unsupported billing entitlement schema")
        return cls(
            enabled=bool(document.get("enabled", True)),
            mode=BillingVerificationMode(str(document.get("mode", BillingVerificationMode.DIGEST.value))),
            billing_api_base_url=document.get("billing_api_base_url"),
            allow_digest_fallback=bool(document.get("allow_digest_fallback", True)),
        )


def digest_entitlement(*, tenant_id: str, principal_id: str, platform_id: str) -> str:
    return sha256(f"{tenant_id}|{principal_id}|{platform_id}|paid".encode()).hexdigest()


def verify_digest_entitlement(
    *,
    tenant_id: str,
    principal_id: str,
    platform_id: str,
    digest: str,
) -> bool:
    if len(digest) != 64 or not all(char in "0123456789abcdef" for char in digest):
        return False
    return digest == digest_entitlement(
        tenant_id=tenant_id,
        principal_id=principal_id,
        platform_id=platform_id,
    )


def verify_billing_api_entitlement(
    *,
    policy: BillingEntitlementPolicy,
    tenant_id: str,
    principal_id: str,
    platform_id: str,
    entitlement_token: str,
) -> bool:
    if not policy.billing_api_base_url:
        return False
    del tenant_id, principal_id, platform_id, entitlement_token
    # Production: HTTPS call to billing SoT. Prototype returns False until configured.
    return False


class BillingEntitlementVerifier:
    def __init__(self, *, foundry_root: Path, policy: BillingEntitlementPolicy | None = None) -> None:
        config = foundry_root / "config" / "arkaon-billing-entitlement.json"
        self.policy = policy or BillingEntitlementPolicy.load(config)

    def verify(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        payment_entitlement_digest: str,
    ) -> bool:
        if not self.policy.enabled:
            return False
        digest_ok = verify_digest_entitlement(
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            digest=payment_entitlement_digest,
        )
        if self.policy.mode is BillingVerificationMode.DIGEST:
            return digest_ok
        api_ok = verify_billing_api_entitlement(
            policy=self.policy,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            entitlement_token=payment_entitlement_digest,
        )
        if self.policy.mode is BillingVerificationMode.BILLING_API:
            return api_ok or (self.policy.allow_digest_fallback and digest_ok)
        return digest_ok or api_ok
