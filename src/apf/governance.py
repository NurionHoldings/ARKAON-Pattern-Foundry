from __future__ import annotations

from dataclasses import dataclass

from .domain import Classification, RiskClass

HIGH_RISK_DOMAINS = frozenset({"SECURITY", "AUTHORIZATION", "PAYMENT", "SETTLEMENT", "PRIVACY"})


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

