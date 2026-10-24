"""Require scope-bound reference consent before co-creation uses external URLs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .reference_material_consent import (
    NOTICE_TEXT,
    NOTICE_VERSION,
)
from .reference_material_consent import (
    digest as reference_digest,
)

_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_CO_CREATION_ALLOWED_DECISIONS = frozenset(
    {
        "REFERENCE_ANALYSIS_ALLOWED",
        "SANDBOX_IMPLEMENTATION_ALLOWED",
    }
)


class ReferenceGateRejected(ValueError):
    def __init__(self, code: str, message: str, *, consent_path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.consent_path = consent_path


def extract_reference_urls(
    *,
    message: str,
    reference_site_url: str | None,
    feature_reference_urls: dict[str, str] | None,
) -> tuple[str, ...]:
    urls: list[str] = []
    if reference_site_url:
        urls.append(reference_site_url.strip())
    if feature_reference_urls:
        urls.extend(str(value).strip() for value in feature_reference_urls.values() if str(value).strip())
    urls.extend(match.group(0).rstrip(".,)") for match in _URL_IN_TEXT.finditer(message))
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            deduped.append(url)
    return tuple(deduped)


def reference_scope_digest(*, urls: tuple[str, ...], intended_use: str) -> str:
    body = {"urls": list(urls), "intended_use": intended_use}
    return reference_digest(body)


def verify_receipt_integrity(receipt: dict[str, Any]) -> tuple[bool, str]:
    if receipt.get("schema_version") != "apf.reference-material-consent-receipt/1.0":
        return False, "RECEIPT_SCHEMA"
    stored = receipt.get("receipt_digest")
    if not isinstance(stored, str) or not stored.startswith("sha256:"):
        return False, "RECEIPT_DIGEST_MISSING"
    body = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    if reference_digest(body) != stored:
        return False, "RECEIPT_DIGEST_MISMATCH"
    if receipt.get("notice_version") != NOTICE_VERSION:
        return False, "NOTICE_VERSION_MISMATCH"
    if receipt.get("notice_digest") != reference_digest(NOTICE_TEXT):
        return False, "NOTICE_DIGEST_MISMATCH"
    decision = receipt.get("decision")
    if not isinstance(decision, dict):
        return False, "DECISION_MISSING"
    if decision.get("request_digest") != receipt.get("request_digest"):
        return False, "REQUEST_DIGEST_MISMATCH"
    if decision.get("consent_digest") != receipt.get("consent_digest"):
        return False, "CONSENT_DIGEST_MISMATCH"
    return True, "ok"


def receipt_allows_co_creation_reference(receipt: dict[str, Any]) -> tuple[bool, str]:
    decision = receipt.get("decision")
    if not isinstance(decision, dict):
        return False, "DECISION_MISSING"
    code = str(decision.get("decision", ""))
    if code == "BLOCKED":
        return False, str(decision.get("reason", "BLOCKED"))
    if code not in _CO_CREATION_ALLOWED_DECISIONS:
        return False, "DECISION_NOT_ALLOWED_FOR_CO_CREATION"
    if code == "SANDBOX_IMPLEMENTATION_ALLOWED" and decision.get("implementation_allowed") is not True:
        return False, "IMPLEMENTATION_NOT_ALLOWED"
    return True, code


def _load_receipt(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def find_valid_receipt(
    *,
    foundry_root: Path,
    request_id: str,
    scope_digest: str,
    principal_id: str,
) -> dict[str, Any] | None:
    path = foundry_root / "state" / "reference-material-consents" / f"{request_id}.json"
    receipt = _load_receipt(path)
    if receipt is None:
        return None
    ok, _reason = verify_receipt_integrity(receipt)
    if not ok:
        return None
    if receipt.get("scope_digest") != scope_digest:
        return None
    if str(receipt.get("principal_id", "")) != principal_id:
        return None
    allowed, _code = receipt_allows_co_creation_reference(receipt)
    if not allowed:
        return None
    return receipt


def assert_reference_consent_or_raise(
    *,
    foundry_root: Path,
    principal_id: str,
    message: str,
    reference_site_url: str | None,
    feature_reference_urls: dict[str, str] | None,
    reference_consent_request_id: str | None,
    intended_use: str,
) -> dict[str, Any] | None:
    urls = extract_reference_urls(
        message=message,
        reference_site_url=reference_site_url,
        feature_reference_urls=feature_reference_urls,
    )
    if not urls:
        return None
    scope = reference_scope_digest(urls=urls, intended_use=intended_use)
    if not reference_consent_request_id:
        raise ReferenceGateRejected(
            "REFERENCE_CONSENT_REQUIRED",
            "reference URL use requires scope-bound consent receipt",
            consent_path="/reference-material-consent",
        )
    receipt = find_valid_receipt(
        foundry_root=foundry_root,
        request_id=reference_consent_request_id,
        scope_digest=scope,
        principal_id=principal_id,
    )
    if receipt is None:
        raise ReferenceGateRejected(
            "REFERENCE_CONSENT_SCOPE_MISMATCH",
            "consent receipt missing, tampered, or not allowed for co-creation reference use",
            consent_path="/reference-material-consent",
        )
    decision = receipt.get("decision")
    if (
        isinstance(decision, dict)
        and decision.get("direct_expression_reuse_allowed") is True
        and decision.get("rights_basis") in (None, "UNKNOWN")
        and not receipt.get("rights_evidence_digest")
    ):
        raise ReferenceGateRejected(
            "REFERENCE_REUSE_RIGHTS_REQUIRED",
            "direct reuse requires documented rights basis",
            consent_path="/reference-material-consent",
        )
    return receipt


def consent_resume_query(*, return_path: str, stash_key: str) -> str:
    safe_path = return_path if return_path.startswith("/services/") else "/services/co-create.html"
    return f"/reference-material-consent?return={urlparse(safe_path).path}&stash={stash_key}"
