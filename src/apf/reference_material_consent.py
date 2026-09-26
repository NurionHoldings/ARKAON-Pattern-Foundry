"""Scope-bound user consent for lawful reference-material use."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field


class ReferenceConsentError(ValueError):
    pass


class ReferenceUseMode(StrEnum):
    PRINCIPLE_REFERENCE = "PRINCIPLE_REFERENCE"
    CLEAN_ROOM_IMPLEMENTATION = "CLEAN_ROOM_IMPLEMENTATION"
    DIRECT_REUSE = "DIRECT_REUSE"


class RightsBasis(StrEnum):
    USER_OWNED = "USER_OWNED"
    EXPLICIT_PERMISSION = "EXPLICIT_PERMISSION"
    LICENSED = "LICENSED"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    UNKNOWN = "UNKNOWN"


REQUIRED_ACKNOWLEDGEMENTS = frozenset(
    {
        "USER_REQUESTED_SPECIFIC_USE",
        "USER_RESPONSIBLE_FOR_MATERIAL_AND_RIGHTS_CLAIM",
        "CONSENT_DOES_NOT_MAKE_UNAUTHORIZED_USE_LAWFUL",
        "PLATFORM_MAY_REFUSE_OR_QUARANTINE",
        "MERGE_AND_DEPLOYMENT_NOT_AUTHORIZED",
    }
)

NOTICE_VERSION = "apf.reference-material-notice/1.0"
NOTICE_TEXT = (
    "사용자가 지정·제공한 참고자료와 권리 주장에 관한 귀책사유가 있으면 사용자가 그 책임을 "
    "부담할 수 있습니다. 이 확인은 무단 이용을 적법하게 만들거나 플랫폼의 책임을 전부 "
    "사용자에게 이전하지 않습니다. 권리가 불명확하거나 침해 가능성이 높으면 구현을 거절하거나 "
    "격리할 수 있으며, 이 확인은 병합·배포 승인이 아닙니다."
)

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ReferenceUseRequest(BaseModel):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
    source_id: str = Field(min_length=1, max_length=200)
    source_locator: str = Field(min_length=1, max_length=2000)
    intended_use: str = Field(min_length=10, max_length=2000)
    mode: ReferenceUseMode
    rights_basis: RightsBasis
    rights_evidence_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    contains_personal_data: bool = False
    contains_secret_or_private_material: bool = False
    bypasses_access_control: bool = False
    requested_paths: list[str] = Field(min_length=1, max_length=50)
    scope_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ReferenceUseConsent(BaseModel):
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    notice_version: str = Field(pattern=r"^apf\.reference-material-notice/1\.0$")
    acknowledged_items: set[str]
    principal_id: UUID
    nonce: UUID
    confirmed_at: datetime


class ReferenceUseDecision(BaseModel):
    decision: str
    reason: str
    allowed_mode: ReferenceUseMode | None
    request_digest: str
    consent_digest: str
    direct_expression_reuse_allowed: bool
    implementation_allowed: bool
    merge_allowed: bool = False
    deployment_allowed: bool = False


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def decide_reference_use(
    request: ReferenceUseRequest, consent: ReferenceUseConsent,
) -> ReferenceUseDecision:
    request_digest = digest(request.model_dump(mode="json"))
    consent_digest = digest(consent.model_dump(mode="json"))
    if consent.request_digest != request_digest:
        raise ReferenceConsentError("REFERENCE_CONSENT_SCOPE_MISMATCH")
    if consent.notice_version != NOTICE_VERSION or consent.acknowledged_items != REQUIRED_ACKNOWLEDGEMENTS:
        raise ReferenceConsentError("REFERENCE_CONSENT_INCOMPLETE")
    if consent.confirmed_at.tzinfo is None or consent.confirmed_at > datetime.now(UTC):
        raise ReferenceConsentError("REFERENCE_CONSENT_TIME_INVALID")
    if request.contains_personal_data or request.contains_secret_or_private_material:
        return _blocked(request, request_digest, consent_digest, "REFERENCE_SENSITIVE_MATERIAL_BLOCKED")
    if request.bypasses_access_control:
        return _blocked(request, request_digest, consent_digest, "REFERENCE_ACCESS_BYPASS_BLOCKED")
    if request.mode == ReferenceUseMode.DIRECT_REUSE:
        if request.rights_basis == RightsBasis.UNKNOWN or request.rights_evidence_digest is None:
            return _blocked(request, request_digest, consent_digest, "REFERENCE_REUSE_RIGHTS_REQUIRED")
        return _allowed(request, request_digest, consent_digest, direct=True)
    if request.mode == ReferenceUseMode.CLEAN_ROOM_IMPLEMENTATION:
        return _allowed(request, request_digest, consent_digest, direct=False)
    return ReferenceUseDecision(
        decision="REFERENCE_ANALYSIS_ALLOWED",
        reason="USER_REQUEST_AND_NOTICE_CONFIRMED",
        allowed_mode=request.mode,
        request_digest=request_digest,
        consent_digest=consent_digest,
        direct_expression_reuse_allowed=False,
        implementation_allowed=False,
    )


class ReferenceConsentStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def verify_analysis_receipt(
        self, request_id: str, *, principal_id: str, source_id: str,
        source_locator: str, scope_digest: str,
    ) -> dict[str, object]:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}", request_id):
            raise ReferenceConsentError("REFERENCE_CONSENT_NOT_FOUND")
        try:
            receipt = json.loads(
                (self.root / "state" / "reference-material-consents" / f"{request_id}.json")
                .read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ReferenceConsentError("REFERENCE_CONSENT_NOT_FOUND") from exc
        if not isinstance(receipt, dict):
            raise ReferenceConsentError("REFERENCE_CONSENT_INVALID")
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if (
            receipt.get("schema_version") != "apf.reference-material-consent-receipt/1.0"
            or receipt.get("receipt_digest") != digest(unsigned)
            or receipt.get("notice_version") != NOTICE_VERSION
            or receipt.get("notice_digest") != digest(NOTICE_TEXT)
            or receipt.get("mode") != ReferenceUseMode.PRINCIPLE_REFERENCE.value
            or receipt.get("decision", {}).get("decision") != "REFERENCE_ANALYSIS_ALLOWED"
        ):
            raise ReferenceConsentError("REFERENCE_CONSENT_INVALID")
        if (
            receipt.get("principal_id") != principal_id
            or receipt.get("source_id") != source_id
            or receipt.get("source_locator") != source_locator
            or receipt.get("scope_digest") != scope_digest
        ):
            raise ReferenceConsentError("REFERENCE_CONSENT_SCOPE_MISMATCH")
        return receipt

    def record(
        self, request: ReferenceUseRequest, consent: ReferenceUseConsent,
    ) -> dict[str, object]:
        decision = decide_reference_use(request, consent)
        receipt = {
            "schema_version": "apf.reference-material-consent-receipt/1.0",
            "request_id": request.request_id,
            "source_id": request.source_id,
            "source_locator": request.source_locator,
            "mode": request.mode.value,
            "rights_basis": request.rights_basis.value,
            "rights_evidence_digest": request.rights_evidence_digest,
            "scope_digest": request.scope_digest,
            "request_digest": decision.request_digest,
            "consent_digest": decision.consent_digest,
            "principal_id": str(consent.principal_id),
            "nonce": str(consent.nonce),
            "confirmed_at": consent.confirmed_at.isoformat(),
            "notice_version": NOTICE_VERSION,
            "notice_digest": digest(NOTICE_TEXT),
            "decision": decision.model_dump(mode="json"),
        }
        receipt["receipt_digest"] = digest(receipt)
        _exclusive_json(
            self.root / "state" / "reference-material-consents" / f"{request.request_id}.json",
            receipt,
        )
        return receipt


def _blocked(
    request: ReferenceUseRequest, request_digest: str, consent_digest: str, reason: str,
) -> ReferenceUseDecision:
    return ReferenceUseDecision(
        decision="BLOCKED", reason=reason, allowed_mode=None,
        request_digest=request_digest, consent_digest=consent_digest,
        direct_expression_reuse_allowed=False, implementation_allowed=False,
    )


def _allowed(
    request: ReferenceUseRequest, request_digest: str, consent_digest: str, *, direct: bool,
) -> ReferenceUseDecision:
    return ReferenceUseDecision(
        decision="SANDBOX_IMPLEMENTATION_ALLOWED",
        reason="RIGHTS_EVIDENCE_VERIFIED" if direct else "USER_REQUESTED_CLEAN_ROOM_IMPLEMENTATION",
        allowed_mode=request.mode, request_digest=request_digest, consent_digest=consent_digest,
        direct_expression_reuse_allowed=direct, implementation_allowed=True,
    )


def _exclusive_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ReferenceConsentError("REFERENCE_CONSENT_ALREADY_RECORDED") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
