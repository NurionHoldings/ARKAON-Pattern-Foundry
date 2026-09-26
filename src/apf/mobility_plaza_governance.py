"""Governance audit for rider mobility plazas: consent, forbidden uses, advisory-only occupancy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .mobility_plaza import ForbiddenPlazaUse, MobilityPlazaFoundation


class PlazaGovernanceRejected(ValueError):
    pass


class GovernanceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class MobilityPlazaGovernancePolicy:
    production_dispatch_from_plaza: bool = False
    presence_surveillance_allowed: bool = False
    continuous_tracking_allowed: bool = False
    max_membership_ttl_hours: int = 12
    max_notice_ttl_hours: int = 24
    max_advisory_occupancy_threshold: int = 64
    forbidden_uses: frozenset[str] = frozenset()

    @classmethod
    def load(cls, path: Path) -> MobilityPlazaGovernancePolicy:
        if not path.is_file():
            return cls(forbidden_uses=frozenset(item.value for item in ForbiddenPlazaUse))
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-mobility-plaza-governance/v1":
            raise PlazaGovernanceRejected("unsupported mobility plaza governance schema")
        if (
            document.get("production_dispatch_from_plaza")
            or document.get("presence_surveillance_allowed")
            or document.get("continuous_tracking_allowed")
        ):
            raise PlazaGovernanceRejected("plaza governance must forbid dispatch and surveillance")
        return cls(
            production_dispatch_from_plaza=bool(document.get("production_dispatch_from_plaza")),
            presence_surveillance_allowed=bool(document.get("presence_surveillance_allowed")),
            continuous_tracking_allowed=bool(document.get("continuous_tracking_allowed")),
            max_membership_ttl_hours=int(document.get("max_membership_ttl_hours", 12)),
            max_notice_ttl_hours=int(document.get("max_notice_ttl_hours", 24)),
            max_advisory_occupancy_threshold=int(document.get("max_advisory_occupancy_threshold", 64)),
            forbidden_uses=frozenset(document.get("forbidden_uses") or ()),
        )


@dataclass(frozen=True)
class PlazaGovernanceFinding:
    finding_id: str
    severity: str
    message: str


@dataclass(frozen=True)
class PlazaGovernanceReport:
    platform_id: str
    evaluated_at: datetime
    findings: tuple[PlazaGovernanceFinding, ...]
    overall: GovernanceStatus
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.plaza-governance-report/v1",
            "platform_id": self.platform_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "overall": self.overall.value,
            "report_digest": self.report_digest,
            "findings": [
                {"finding_id": item.finding_id, "severity": item.severity, "message": item.message}
                for item in self.findings
            ],
        }


class PlazaGovernanceHarness:
    """Audits plaza foundation state and optional platform config against governance policy."""

    def __init__(self, *, foundry_root: Path, policy: MobilityPlazaGovernancePolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy = policy or MobilityPlazaGovernancePolicy.load(
            self.foundry_root / "config" / "arkaon-mobility-plaza-governance.json"
        )

    def audit_foundation(
        self,
        *,
        platform_id: str,
        foundation: MobilityPlazaFoundation,
        now: datetime,
    ) -> PlazaGovernanceReport:
        if now.tzinfo is None:
            raise PlazaGovernanceRejected("timezone-aware timestamp required")
        findings: list[PlazaGovernanceFinding] = []
        for plaza_id in getattr(foundation, "_plazas", {}):
            occupancy = foundation.occupancy(plaza_id=plaza_id, now=now)
            if occupancy.usable_for_dispatch:
                findings.append(
                    PlazaGovernanceFinding(
                        "dispatch-from-occupancy",
                        "BLOCKER",
                        "occupancy must not be usable for dispatch",
                    )
                )
            if occupancy.identities_disclosed:
                findings.append(
                    PlazaGovernanceFinding(
                        "identity-disclosure",
                        "BLOCKER",
                        "occupancy must not disclose identities",
                    )
                )
            if occupancy.member_count > self.policy.max_advisory_occupancy_threshold:
                findings.append(
                    PlazaGovernanceFinding(
                        "high-occupancy-advisory",
                        "MEDIUM",
                        f"occupancy {occupancy.member_count} exceeds advisory threshold",
                    )
                )
        for notice in getattr(foundation, "_notices", {}).values():
            if notice.dispatch_signal:
                findings.append(
                    PlazaGovernanceFinding(
                        f"notice-dispatch-{notice.notice_id}",
                        "BLOCKER",
                        "plaza notice must not carry dispatch signal",
                    )
                )
            if notice.expires_at - notice.created_at > timedelta(hours=self.policy.max_notice_ttl_hours):
                findings.append(
                    PlazaGovernanceFinding(
                        f"notice-ttl-{notice.notice_id}",
                        "HIGH",
                        "notice TTL exceeds governance bound",
                    )
                )
        overall = GovernanceStatus.FAIL if findings else GovernanceStatus.PASS
        digest_source = {
            "platform_id": platform_id,
            "overall": overall.value,
            "finding_ids": [item.finding_id for item in findings],
        }
        report_digest = sha256(json.dumps(digest_source, sort_keys=True).encode()).hexdigest()
        return PlazaGovernanceReport(platform_id, now, tuple(findings), overall, report_digest)

    def audit_platform_config(self, *, platform_id: str, platform_path: Path, now: datetime) -> PlazaGovernanceReport | None:
        config_path = platform_path / "config" / "mobility-plaza.json"
        if not config_path.is_file():
            return None
        document = json.loads(config_path.read_text(encoding="utf-8"))
        findings: list[PlazaGovernanceFinding] = []
        if document.get("dispatch_from_plaza") or document.get("continuous_tracking"):
            findings.append(
                PlazaGovernanceFinding(
                    "platform-config-forbidden",
                    "BLOCKER",
                    "platform plaza config requests forbidden dispatch or tracking",
                )
            )
        overall = GovernanceStatus.FAIL if findings else GovernanceStatus.PASS
        digest_source = {"platform_id": platform_id, "config": config_path.name, "findings": len(findings)}
        report_digest = sha256(json.dumps(digest_source, sort_keys=True).encode()).hexdigest()
        return PlazaGovernanceReport(platform_id, now, tuple(findings), overall, report_digest)
