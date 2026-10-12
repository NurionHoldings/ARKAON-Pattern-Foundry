"""ARKAON public-surface self-heal: detect gaps, request Beom/Eternian/admin, inbox only."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path


class PlatformSelfHealRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SelfHealSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SelfHealAssignee(str, Enum):
    BEOM = "beom"
    ETERNIAN = "eternian"
    ADMIN = "admin"


@dataclass(frozen=True)
class SelfHealFinding:
    gap_code: str
    severity: SelfHealSeverity
    summary: str
    needed_from_admin: str
    assignee: SelfHealAssignee
    self_heal_step: str

    def to_document(self) -> dict[str, object]:
        return {
            "gap_code": self.gap_code,
            "severity": self.severity.value,
            "summary": self.summary,
            "needed_from_admin": self.needed_from_admin,
            "assignee": self.assignee.value,
            "self_heal_step": self.self_heal_step,
        }


@dataclass(frozen=True)
class PlatformSelfHealPolicy:
    platform_id: str = "ARKAON_FOUNDRY"
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False
    beom_codes: frozenset[str] = frozenset()
    eternian_codes: frozenset[str] = frozenset()

    @classmethod
    def load(cls, path: Path) -> PlatformSelfHealPolicy:
        if not path.is_file():
            return cls(
                beom_codes=frozenset(
                    {
                        "API_CONSOLE_UNREACHABLE",
                        "API_HEALTH_MISSING",
                        "FOUNDRY_API_NOT_CONFIGURED",
                    }
                ),
                eternian_codes=frozenset({"UX_CLAIM_MISMATCH"}),
            )
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.platform-self-heal/v1":
            raise PlatformSelfHealRejected("POLICY_SCHEMA", "unsupported platform self-heal schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise PlatformSelfHealRejected("POLICY_FORBIDDEN", "self-heal must remain request-only")
        return cls(
            platform_id=str(document.get("platform_id", "ARKAON_FOUNDRY")),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            beom_codes=frozenset(document.get("beom_assignee_gap_codes") or ()),
            eternian_codes=frozenset(document.get("eternian_assignee_gap_codes") or ()),
        )


def _default_assignee(policy: PlatformSelfHealPolicy, gap_code: str) -> SelfHealAssignee:
    if gap_code in policy.beom_codes:
        return SelfHealAssignee.BEOM
    if gap_code in policy.eternian_codes:
        return SelfHealAssignee.ETERNIAN
    return SelfHealAssignee.ADMIN


def finding_from_payload(
    payload: dict[str, object], *, policy: PlatformSelfHealPolicy
) -> SelfHealFinding:
    gap_code = str(payload.get("gap_code", "")).strip()
    if not gap_code or len(gap_code) > 64:
        raise PlatformSelfHealRejected("GAP_CODE", "gap_code required")
    try:
        severity = SelfHealSeverity(str(payload.get("severity", "")))
    except ValueError as error:
        raise PlatformSelfHealRejected("SEVERITY", "invalid severity") from error
    summary = str(payload.get("summary", "")).strip()[:2000]
    needed = str(payload.get("needed_from_admin", "")).strip()[:2000]
    step = str(payload.get("self_heal_step", "")).strip()[:2000]
    if not summary or not needed:
        raise PlatformSelfHealRejected("TEXT", "summary and needed_from_admin required")
    assignee_raw = str(payload.get("assignee", "")).strip().lower()
    if assignee_raw in {a.value for a in SelfHealAssignee}:
        assignee = SelfHealAssignee(assignee_raw)
    else:
        assignee = _default_assignee(policy, gap_code)
    return SelfHealFinding(
        gap_code=gap_code,
        severity=severity,
        summary=summary,
        needed_from_admin=needed,
        assignee=assignee,
        self_heal_step=step or "승인 후 Foundry·정적 호스트에 단계 반영",
    )


def assess_static_platform(foundry_root: Path) -> tuple[SelfHealFinding, ...]:
    """Repository-local checks for public home/service consistency."""
    policy = PlatformSelfHealPolicy.load(foundry_root / "config" / "arkaon-platform-self-heal.json")
    findings: list[SelfHealFinding] = []
    catalog_path = foundry_root / "config" / "arkaon-home-services.json"
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        for service in catalog.get("services") or []:
            href = str(service.get("href", ""))
            if not href.startswith("/"):
                continue
            target = foundry_root / href.lstrip("/")
            if not target.is_file():
                findings.append(
                    SelfHealFinding(
                        gap_code="BROKEN_SERVICE_PATH",
                        severity=SelfHealSeverity.BLOCKER,
                        summary=f"서비스 '{service.get('title')}' 경로가 없습니다: {href}",
                        needed_from_admin="누락된 /services 페이지를 복구하거나 카탈로그 href를 수정해 주세요.",
                        assignee=SelfHealAssignee.BEOM,
                        self_heal_step="파일 배포·카탈로그 정합 후 재진단",
                    )
                )
            status = str(service.get("status", ""))
            title = str(service.get("title", ""))
            if status == "available" and service.get("id") in {
                "co-create",
                "account",
                "admin",
            }:
                findings.append(
                    SelfHealFinding(
                        gap_code="UX_CLAIM_MISMATCH",
                        severity=SelfHealSeverity.HIGH,
                        summary=f"'{title}'이(가) 이용 가능으로 표시되나 Foundry API·세션 없이는 핵심 기능이 제한됩니다.",
                        needed_from_admin="API 동일 출처 프록시 또는 UI 상태(연결 필요) 표현을 정리해 주세요.",
                        assignee=_default_assignee(policy, "UX_CLAIM_MISMATCH"),
                        self_heal_step="카피·상태 배지 정합 또는 API 연동",
                    )
                )
    api_hints = foundry_root / "config" / "arkaon-public-api.json"
    if api_hints.is_file():
        hints = json.loads(api_hints.read_text(encoding="utf-8"))
        note = str(hints.get("note", ""))
        if "Netlify" in note and "별도" in note:
            findings.append(
                SelfHealFinding(
                    gap_code="FOUNDRY_API_NOT_CONFIGURED",
                    severity=SelfHealSeverity.HIGH,
                    summary="공개 정적 호스트와 Foundry API가 분리되어 있습니다.",
                    needed_from_admin="범: Foundry API URL·리버스 프록시 또는 Netlify proxy 규칙을 설정해 주세요.",
                    assignee=SelfHealAssignee.BEOM,
                    self_heal_step="account 화면 API URL + /health·/console 검증",
                )
            )
    return tuple(findings)


def _requested_actions(
    finding: SelfHealFinding, *, platform_id: str, packet_id: str
) -> tuple[dict[str, object], ...]:
    gap_slug = finding.gap_code.lower().replace("_", "-")
    base = f"{packet_id}-{gap_slug}"
    stage_for = {
        SelfHealAssignee.BEOM: "operator-decision",
        SelfHealAssignee.ETERNIAN: "eternian-review",
        SelfHealAssignee.ADMIN: "operator-decision",
    }
    kind_for = {
        SelfHealAssignee.BEOM: "OPERATOR_DECISION",
        SelfHealAssignee.ETERNIAN: "ETERNIAN_REVIEW",
        SelfHealAssignee.ADMIN: "OPERATOR_DECISION",
    }
    label = {"beom": "범", "eternian": "에테르니언", "admin": "관리자"}[finding.assignee.value]
    return (
        {
            "action_id": f"{base}-request",
            "inbox_stage": "research",
            "kind": "RESEARCH",
            "summary": (
                f"{platform_id}: [{finding.gap_code}] ARKAON 자가치유 — "
                f"{finding.summary[:180]}"
            ),
        },
        {
            "action_id": f"{base}-fulfill",
            "inbox_stage": stage_for[finding.assignee],
            "kind": kind_for[finding.assignee],
            "summary": (
                f"{platform_id}: {label}에게 필요 — {finding.needed_from_admin[:200]}"
            ),
        },
    )


def ingest_surface_report(
    *,
    foundry_root: Path,
    platform_id: str,
    surface_url: str,
    finding_payloads: tuple[dict[str, object], ...],
    now: datetime,
    include_static_assessment: bool = True,
) -> dict[str, object]:
    if now.tzinfo is None:
        raise PlatformSelfHealRejected("TIMESTAMP", "timezone-aware timestamp required")
    if not finding_payloads:
        raise PlatformSelfHealRejected("FINDINGS", "at least one finding required")
    policy = PlatformSelfHealPolicy.load(foundry_root / "config" / "arkaon-platform-self-heal.json")
    if platform_id != policy.platform_id and platform_id != "ARKAON_FOUNDRY":
        raise PlatformSelfHealRejected("PLATFORM", "unsupported platform_id")

    merged: list[SelfHealFinding] = []
    seen_codes: set[str] = set()
    if include_static_assessment:
        for item in assess_static_platform(foundry_root):
            if item.gap_code not in seen_codes:
                merged.append(item)
                seen_codes.add(item.gap_code)
    for payload in finding_payloads:
        finding = finding_from_payload(payload, policy=policy)
        if finding.gap_code in seen_codes:
            continue
        merged.append(finding)
        seen_codes.add(finding.gap_code)

    if not merged:
        raise PlatformSelfHealRejected("FINDINGS", "no findings after merge")

    packet_id = secrets.token_hex(8)
    findings_docs = [item.to_document() for item in merged]
    actions: list[dict[str, object]] = []
    for finding in merged:
        actions.extend(_requested_actions(finding, platform_id=platform_id, packet_id=packet_id))

    document: dict[str, object] = {
        "schema_version": "apf.platform-self-heal-request/v1",
        "packet_id": packet_id,
        "platform_id": platform_id,
        "summary": f"ARKAON 자가치유 요청 {len(merged)}건 — {surface_url[:120]}",
        "created_at": now.isoformat(),
        "surface_url": surface_url[:512],
        "finding_count": len(merged),
        "findings": findings_docs,
        "requested_actions": actions,
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "report_digest": sha256(
            json.dumps(findings_docs, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    }

    inbox = foundry_root / "inbox" / "research"
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / f"{packet_id}-{platform_id}-platform-self-heal-research.json"
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    from .arkaon_mailbox import ArkaonMailbox

    mailbox = ArkaonMailbox(foundry_root=foundry_root)
    mailbox.sync_from_inbox(now=now)

    return {
        "packet_id": packet_id,
        "inbox_path": target.relative_to(foundry_root).as_posix(),
        "finding_count": len(merged),
        "report_digest": document["report_digest"],
        "mailbox_pending": len(mailbox.list_items()),
    }
