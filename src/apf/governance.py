from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .domain import Classification, RiskClass

HIGH_RISK_DOMAINS = frozenset({"SECURITY", "AUTHORIZATION", "PAYMENT", "SETTLEMENT", "PRIVACY"})
FOUNDRY_REPOSITORY = "NurionHoldings/ARKAON-Pattern-Foundry"
SAFE_AUTONOMOUS_ACTIONS = frozenset(
    {"analyze", "design", "edit", "test", "commit", "open_pull_request", "fix_ci"}
)


@dataclass(frozen=True)
class AutonomousGrant:
    """Repository-scoped authority granted by the owner for uninterrupted work."""

    granted_by: str
    repository: str
    allowed_actions: frozenset[str]
    revoked: bool = False
    expires_at: datetime | None = None


def can_execute_autonomously(
    grant: AutonomousGrant,
    *,
    repository: str,
    action: str,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Evaluate a standing command without widening it beyond this Foundry repo."""
    current = now or datetime.now(UTC)
    if grant.revoked:
        return False, "GRANT_REVOKED"
    if grant.expires_at is not None and grant.expires_at <= current:
        return False, "GRANT_EXPIRED"
    if grant.repository != FOUNDRY_REPOSITORY or repository != grant.repository:
        return False, "REPOSITORY_OUT_OF_SCOPE"
    if action not in grant.allowed_actions or action not in SAFE_AUTONOMOUS_ACTIONS:
        return False, "ACTION_OUT_OF_SCOPE"
    return True, "AUTHORIZED_STANDING_COMMAND"


@dataclass(frozen=True)
class PublicationGateInput:
    classification: Classification
    derivation_allowed: bool
    evidence_coverage: float
    personal_data_findings: int
    secret_findings: int
    customer_identifier_findings: int
    license_conflicts: int
    critical_security_findings: int
    approval_roles: frozenset[str]
    risk_class: RiskClass
    domains: frozenset[str]


def can_publish(value: PublicationGateInput) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    if value.classification == Classification.PROHIBITED:
        failures.append("PROHIBITED_SOURCE")
    if not value.derivation_allowed:
        failures.append("DERIVATION_NOT_ALLOWED")
    if value.evidence_coverage < 1:
        failures.append("EVIDENCE_INCOMPLETE")
    if value.personal_data_findings:
        failures.append("PERSONAL_DATA_FOUND")
    if value.secret_findings:
        failures.append("SECRET_FOUND")
    if value.customer_identifier_findings:
        failures.append("CUSTOMER_IDENTIFIER_FOUND")
    if value.license_conflicts:
        failures.append("LICENSE_CONFLICT")
    if value.critical_security_findings:
        failures.append("CRITICAL_SECURITY_FINDING")
    required = 2 if value.risk_class in {RiskClass.HIGH, RiskClass.CRITICAL} or value.domains & HIGH_RISK_DOMAINS else 1
    if len(value.approval_roles) < required:
        failures.append("INSUFFICIENT_INDEPENDENT_APPROVALS")
    return not failures, tuple(failures)

