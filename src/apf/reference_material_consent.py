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

NOTICE_VERSION = "apf.reference-material-notice/1.1"
NOTICE_TEXT = (
    "사용자가 지정·제공한 참고자료와 권리 주장에 관한 귀책사유가 있으면 사용자가 그 책임을 "
    "민사상 책임을 부담할 수 있고, 고의 등 법정 요건에 따라 형사책임이 문제될 수 있습니다. "
    "책임의 성립과 범위는 구체적 행위와 법령에 따라 판단됩니다. 이 확인은 무단 이용을 적법하게 만들거나 플랫폼의 책임을 전부 "
    "사용자에게 이전하지 않습니다. 권리가 불명확하거나 침해 가능성이 높으면 구현을 거절하거나 "
    "격리할 수 있으며, 이 확인은 병합·배포 승인이 아닙니다."
)

MODIFICATION_PROPOSALS = (
    "로고·상호·고유 아이콘은 직접 만든 브랜드 자산으로 교체합니다.",
    "사진·영상·삽화는 사용 권한이 확인된 자료로 교체하고 조건과 출처를 기록합니다.",
    "소개문·홍보문·후기·상품 설명은 실제 사용자 자료를 근거로 새로 작성합니다.",
    "페이지 순서·정보 구조·카드 구성·타이포그래피를 목적에 맞게 독립 설계합니다.",
    "예약 단계를 줄이거나 업종별 입력·접근성 기능을 추가하는 등 이용 흐름을 보강합니다.",
    "원본 코드·폰트·라이브러리의 허가 범위와 출처표시·변경·배포 조건을 따로 확인합니다.",
    "색상·글꼴·애니메이션 변경만으로 침해가 해소되거나 일정 변경 비율이면 적법하다고 보장하지 않습니다.",
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
    notice_version: str = Field(pattern=r"^apf\.reference-material-notice/1\.[01]$")
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
    modification_proposals: list[str] = Field(default_factory=lambda: list(MODIFICATION_PROPOSALS))
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

    def record(
        self, request: ReferenceUseRequest, consent: ReferenceUseConsent,
    ) -> dict[str, object]:
        decision = decide_reference_use(request, consent)
        receipt = {
            "schema_version": "apf.reference-material-consent-receipt/1.0",
            "request_id": request.request_id,
            "source_id": request.source_id,
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
        reason="RIGHTS_BASIS_AND_EVIDENCE_RECORDED" if direct else "USER_REQUESTED_CLEAN_ROOM_IMPLEMENTATION",
        allowed_mode=request.mode, request_digest=request_digest, consent_digest=consent_digest,
        direct_expression_reuse_allowed=direct, implementation_allowed=True,
    )


ALLOWED_CONSENT_RETURN_PATHS = frozenset(
    {
        "/services/site-builder.html",
        "/services/co-create.html",
    }
)


def consent_return_url_allowed(return_url: str) -> bool:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(return_url.strip())
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.path not in ALLOWED_CONSENT_RETURN_PATHS:
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1"}:
        return True
    if host == "arkaonfoundry.netlify.app":
        return True
    return host.endswith("--arkaonfoundry.netlify.app")


def normalize_consent_return_url(return_url: str) -> str | None:
    cleaned = return_url.strip()
    if not cleaned or not consent_return_url_allowed(cleaned):
        return None
    return cleaned


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
