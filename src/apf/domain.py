from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class Classification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CLIENT_RESTRICTED = "CLIENT_RESTRICTED"
    PROHIBITED = "PROHIBITED"


class RiskClass(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Decision(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class TargetType(StrEnum):
    OWNED_SYSTEM = "OWNED_SYSTEM"
    CLIENT_DELEGATED = "CLIENT_DELEGATED"
    OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCUMENTATION"
    LICENSED_OPEN_SOURCE = "LICENSED_OPEN_SOURCE"


class TargetState(StrEnum):
    DRAFT = "DRAFT"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    AUTHORIZED = "AUTHORIZED"
    INGESTING = "INGESTING"
    READY = "READY"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class RunState(StrEnum):
    QUEUED = "QUEUED"
    INTENT_SCOPING = "INTENT_SCOPING"
    ANALYZING = "ANALYZING"
    ABSTRACTING = "ABSTRACTING"
    VALIDATING = "VALIDATING"
    REVIEW_PENDING = "REVIEW_PENDING"
    PARTIAL_REVIEW = "PARTIAL_REVIEW"
    COMPLETED = "COMPLETED"
    HOLD = "HOLD"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    QUARANTINED = "QUARANTINED"


class CandidateState(StrEnum):
    DRAFT = "DRAFT"
    EVIDENCE_CHECKED = "EVIDENCE_CHECKED"
    VALIDATED = "VALIDATED"
    REVIEW_PENDING = "REVIEW_PENDING"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"


class ScopePermissions(BaseModel):
    read: bool = True
    parse: bool = False
    derive: bool = False
    publish_common_pattern: bool = False


class AnalysisTargetCreate(BaseModel):
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=200)
    target_type: TargetType
    classification: Classification
    permissions: ScopePermissions
    source_evidence_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_boundaries(self) -> AnalysisTargetCreate:
        if self.classification == Classification.PROHIBITED:
            raise ValueError("PROHIBITED targets cannot be registered for analysis")
        if self.permissions.derive and not self.permissions.parse:
            raise ValueError("derive requires parse permission")
        if self.permissions.publish_common_pattern and not self.permissions.derive:
            raise ValueError("publication requires derivation permission")
        return self


class AnalysisTarget(AnalysisTargetCreate):
    id: UUID = Field(default_factory=uuid4)
    state: TargetState = TargetState.DRAFT
    revision: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class AnalysisBudget(BaseModel):
    max_seconds: int = Field(default=300, gt=0, le=86400)
    max_tokens: int = Field(default=50000, gt=0)
    max_artifacts: int = Field(default=100, gt=0)
    max_depth: int = Field(default=3, ge=1, le=10)


class IntentStatement(BaseModel):
    canonical_text: str = Field(min_length=1)
    evidence_refs: list[UUID] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    stability: str = Field(pattern="^(CORE|CONFIGURABLE|EXPERIMENTAL)$")
    disputed: bool = False


INTENT_AXES = (
    "why", "who", "value", "outcome", "journey", "object", "owner",
    "invariant", "constraint", "risk", "signal", "evolution",
)
CRITICAL_AXES = frozenset({"why", "who", "outcome", "owner", "invariant", "constraint"})


class IntentDNA(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    analysis_run_id: UUID
    axes: dict[str, list[IntentStatement]]
    completeness: float = Field(ge=0, le=1)
    fingerprint: str | None = None
    locked: bool = False

    @model_validator(mode="after")
    def validate_axes(self) -> IntentDNA:
        unknown = set(self.axes) - set(INTENT_AXES)
        if unknown:
            raise ValueError(f"unknown intent axes: {sorted(unknown)}")
        return self


class WorkContract(BaseModel):
    protocol: str = Field(pattern=r"^AFP/0\.1$")
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
    causation_id: UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=200)
    tenant_id: UUID
    classification: Classification
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    task_type: str
    target_snapshot_id: UUID
    artifact_ids: list[UUID]
    objective: str
    non_goals: list[str]
    required_outputs: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    risk_class: RiskClass
    analysis_budget: AnalysisBudget
    authority_scope: list[str]
    stop_conditions: list[str]

    @model_validator(mode="after")
    def not_expired_at_creation(self) -> WorkContract:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        return self


class AnalysisFact(BaseModel):
    statement: str
    evidence_refs: list[UUID] = Field(min_length=1)


class AnalysisInference(BaseModel):
    statement: str
    based_on_fact_indexes: list[int] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ResultContract(BaseModel):
    protocol: str = "AFP/0.1"
    correlation_id: UUID
    status: str
    observed_facts: list[AnalysisFact]
    inferences: list[AnalysisInference]
    unknowns: list[str]
    findings: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
    recommendation: Decision
    content_hash: str

