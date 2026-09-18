"""Payment entitlement verification — digest prototype with billing SoT API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HttpPostFn = Callable[[str, dict[str, str], bytes, int, int], tuple[int, bytes]]


class BillingEntitlementRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BillingVerificationMode(str, Enum):
    DIGEST = "DIGEST"
    BILLING_API = "BILLING_API"
    DIGEST_THEN_API = "DIGEST_THEN_API"


_ENTITLED_STATUSES = frozenset({"ACTIVE", "TRIAL", "PAID"})


@dataclass(frozen=True)
class BillingEntitlementPolicy:
    enabled: bool = True
    mode: BillingVerificationMode = BillingVerificationMode.DIGEST
    billing_api_base_url: str | None = None
    verify_path: str = "/v1/entitlements/verify"
    api_token_env: str = "ARKAON_BILLING_API_TOKEN"
    capability: str = "co_creation"
    allow_digest_fallback: bool = True
    request_timeout_seconds: int = 10
    max_response_bytes: int = 8192

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
            verify_path=str(document.get("verify_path", cls.verify_path)),
            api_token_env=str(document.get("api_token_env", cls.api_token_env)),
            capability=str(document.get("capability", cls.capability)),
            allow_digest_fallback=bool(document.get("allow_digest_fallback", True)),
            request_timeout_seconds=max(1, int(document.get("request_timeout_seconds", 10))),
            max_response_bytes=max(256, int(document.get("max_response_bytes", 8192))),
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


def _canonical_billing_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise BillingEntitlementRejected("BILLING_URL_INSECURE", "billing_api_base_url must be credential-free HTTPS")
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    return f"https://{parsed.hostname.lower()}{port}"


def build_billing_verify_url(*, policy: BillingEntitlementPolicy) -> str:
    if not policy.billing_api_base_url:
        raise BillingEntitlementRejected("BILLING_URL_MISSING", "billing_api_base_url is not configured")
    base = _canonical_billing_base_url(policy.billing_api_base_url)
    path = policy.verify_path if policy.verify_path.startswith("/") else f"/{policy.verify_path}"
    return urlunsplit(("https", urlsplit(base).netloc, path, "", ""))


def _resolve_api_token(policy: BillingEntitlementPolicy) -> str | None:
    token = os.environ.get(policy.api_token_env, "").strip()
    return token or None


def _parse_entitlement_response(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if "entitled" in payload:
        return bool(payload["entitled"])
    status = str(payload.get("status", "")).upper()
    return status in _ENTITLED_STATUSES


def default_http_post(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout_seconds: int,
    max_response_bytes: int,
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, response.read(max_response_bytes)
    except urllib.error.HTTPError as error:
        return error.code, error.read(max_response_bytes)


def verify_billing_api_entitlement(
    *,
    policy: BillingEntitlementPolicy,
    tenant_id: str,
    principal_id: str,
    platform_id: str,
    entitlement_token: str,
    http_post: HttpPostFn = default_http_post,
) -> bool:
    if not policy.billing_api_base_url:
        return False
    api_token = _resolve_api_token(policy)
    if not api_token:
        return False
    try:
        verify_url = build_billing_verify_url(policy=policy)
    except BillingEntitlementRejected:
        return False
    request_body = json.dumps(
        {
            "tenant_id": tenant_id,
            "principal_id": principal_id,
            "platform_id": platform_id,
            "entitlement_token": entitlement_token,
            "capability": policy.capability,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "ARKAON-Pattern-Foundry/0.1",
    }
    try:
        status_code, payload_bytes = http_post(
            verify_url,
            headers,
            request_body,
            policy.request_timeout_seconds,
            policy.max_response_bytes,
        )
    except (TimeoutError, urllib.error.URLError, OSError):
        return False
    if status_code in (401, 403, 404, 402):
        return False
    if status_code != 200:
        return False
    try:
        payload = json.loads(payload_bytes.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return _parse_entitlement_response(payload)


class BillingEntitlementVerifier:
    def __init__(
        self,
        *,
        foundry_root: Path,
        policy: BillingEntitlementPolicy | None = None,
        http_post: HttpPostFn = default_http_post,
    ) -> None:
        config = foundry_root / "config" / "arkaon-billing-entitlement.json"
        self.policy = policy or BillingEntitlementPolicy.load(config)
        self._http_post = http_post

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
            http_post=self._http_post,
        )
        if self.policy.mode is BillingVerificationMode.BILLING_API:
            return api_ok or (self.policy.allow_digest_fallback and digest_ok)
        return digest_ok or api_ok
