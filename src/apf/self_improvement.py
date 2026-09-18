"""Owner-governed ARKAON self-improvement request workflow."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from .evidence_capability import (
    CapabilityTier,
    CollectedEvidence,
    limit_capabilities,
)


class ImprovementActor(StrEnum):
    ARKAON = "ARKAON"
    ETERNIAN = "ETERNIAN"
    OWNER = "OWNER"
    # Retained only for reading legacy records. New verification authority is
    # split explicitly between ARKAON and ETERNIAN.
    VERIFIER = "VERIFIER"


class ImprovementState(StrEnum):
    DETECTED = "DETECTED"
    INBOX_POSTED = "INBOX_POSTED"
    ETERNIAN_REVIEWING = "ETERNIAN_REVIEWING"
    OWNER_APPROVAL_PENDING = "OWNER_APPROVAL_PENDING"
    OWNER_APPROVED = "OWNER_APPROVED"
    SANDBOX_IMPLEMENTING = "SANDBOX_IMPLEMENTING"
    ARKAON_VERIFYING = "ARKAON_VERIFYING"
    ARKAON_VERIFIED = "ARKAON_VERIFIED"
    ETERNIAN_AUDITING = "ETERNIAN_AUDITING"
    ETERNIAN_REMEDIATING = "ETERNIAN_REMEDIATING"
    ETERNIAN_VERIFIED = "ETERNIAN_VERIFIED"
    CHANGE_REPORTED = "CHANGE_REPORTED"
    DEPLOYMENT_APPROVAL_PENDING = "DEPLOYMENT_APPROVAL_PENDING"
    HOLD = "HOLD"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class ImprovementWorkflowError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SelfImprovementRequest:
    request_id: str
    state: ImprovementState
    revision: int
    detected_at: datetime
    updated_at: datetime
    intent_dna: str
    capability_gap: str
    evidence_refs: tuple[str, ...]
    proposed_change: str
    expected_benefit: str
    risks: tuple[str, ...]
    validation_plan: tuple[str, ...]
    source_tier: CapabilityTier
    owner_approval_digest: str | None = None
    arkaon_verification_digest: str | None = None
    eternian_audit_digest: str | None = None
    eternian_remediation_digest: str | None = None
    production_change_allowed: bool = False
    automatic_merge_allowed: bool = False
    deployment_allowed: bool = False

    def scope_document(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "intent_dna": self.intent_dna,
            "capability_gap": self.capability_gap,
            "evidence_refs": list(self.evidence_refs),
            "proposed_change": self.proposed_change,
            "expected_benefit": self.expected_benefit,
            "risks": list(self.risks),
            "validation_plan": list(self.validation_plan),
            "source_tier": self.source_tier.value,
        }

    def scope_digest(self) -> str:
        payload = json.dumps(
            self.scope_document(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode()).hexdigest()

    def to_document(self) -> dict[str, object]:
        document = asdict(self)
        document["schema_version"] = "apf.self-improvement-request/1.0"
        document["state"] = self.state.value
        document["source_tier"] = self.source_tier.value
        document["detected_at"] = self.detected_at.isoformat()
        document["updated_at"] = self.updated_at.isoformat()
        document["evidence_refs"] = list(self.evidence_refs)
        document["risks"] = list(self.risks)
        document["validation_plan"] = list(self.validation_plan)
        document["scope_digest"] = self.scope_digest()
        return document


def detect_self_improvement(
    *,
    request_id: str,
    now: datetime,
    intent_dna: str,
    capability_gap: str,
    evidence_refs: tuple[str, ...],
    proposed_change: str,
    expected_benefit: str,
    risks: tuple[str, ...],
    validation_plan: tuple[str, ...],
    evidence: CollectedEvidence,
) -> SelfImprovementRequest:
    decision = limit_capabilities(evidence)
    if not decision.allows("DESIGN_IMPROVEMENT"):
        raise ImprovementWorkflowError("EVIDENCE_NOT_READY_FOR_IMPROVEMENT_REQUEST")
    required_text = (request_id, intent_dna, capability_gap, proposed_change, expected_benefit)
    if any(not value.strip() for value in required_text):
        raise ImprovementWorkflowError("COMPLETE_IMPROVEMENT_SCOPE_REQUIRED")
    if not evidence_refs or not validation_plan:
        raise ImprovementWorkflowError("EVIDENCE_AND_VALIDATION_REQUIRED")
    if now.tzinfo is None:
        raise ImprovementWorkflowError("TIMEZONE_AWARE_TIME_REQUIRED")
    return SelfImprovementRequest(
        request_id=request_id,
        state=ImprovementState.DETECTED,
        revision=0,
        detected_at=now,
        updated_at=now,
        intent_dna=intent_dna,
        capability_gap=capability_gap,
        evidence_refs=evidence_refs,
        proposed_change=proposed_change,
        expected_benefit=expected_benefit,
        risks=risks,
        validation_plan=validation_plan,
        source_tier=decision.tier,
    )


_ALLOWED_TRANSITIONS: dict[
    ImprovementState, dict[ImprovementState, ImprovementActor]
] = {
    ImprovementState.DETECTED: {
        ImprovementState.INBOX_POSTED: ImprovementActor.ARKAON,
        ImprovementState.BLOCKED: ImprovementActor.ARKAON,
    },
    ImprovementState.INBOX_POSTED: {
        ImprovementState.ETERNIAN_REVIEWING: ImprovementActor.ETERNIAN,
        ImprovementState.EXPIRED: ImprovementActor.ETERNIAN,
        ImprovementState.SUPERSEDED: ImprovementActor.ETERNIAN,
    },
    ImprovementState.ETERNIAN_REVIEWING: {
        ImprovementState.OWNER_APPROVAL_PENDING: ImprovementActor.ETERNIAN,
        ImprovementState.HOLD: ImprovementActor.ETERNIAN,
        ImprovementState.REJECTED: ImprovementActor.ETERNIAN,
        ImprovementState.BLOCKED: ImprovementActor.ETERNIAN,
    },
    ImprovementState.OWNER_APPROVAL_PENDING: {
        ImprovementState.OWNER_APPROVED: ImprovementActor.OWNER,
        ImprovementState.HOLD: ImprovementActor.OWNER,
        ImprovementState.REJECTED: ImprovementActor.OWNER,
    },
    ImprovementState.OWNER_APPROVED: {
        ImprovementState.SANDBOX_IMPLEMENTING: ImprovementActor.ARKAON,
    },
    ImprovementState.SANDBOX_IMPLEMENTING: {
        ImprovementState.ARKAON_VERIFYING: ImprovementActor.ARKAON,
        ImprovementState.FAILED: ImprovementActor.ARKAON,
    },
    ImprovementState.ARKAON_VERIFYING: {
        ImprovementState.ARKAON_VERIFIED: ImprovementActor.ARKAON,
        ImprovementState.FAILED: ImprovementActor.ARKAON,
    },
    ImprovementState.ARKAON_VERIFIED: {
        ImprovementState.ETERNIAN_AUDITING: ImprovementActor.ETERNIAN,
    },
    ImprovementState.ETERNIAN_AUDITING: {
        ImprovementState.ETERNIAN_REMEDIATING: ImprovementActor.ETERNIAN,
        ImprovementState.ETERNIAN_VERIFIED: ImprovementActor.ETERNIAN,
        ImprovementState.HOLD: ImprovementActor.ETERNIAN,
        ImprovementState.BLOCKED: ImprovementActor.ETERNIAN,
        ImprovementState.FAILED: ImprovementActor.ETERNIAN,
    },
    ImprovementState.ETERNIAN_REMEDIATING: {
        ImprovementState.ETERNIAN_VERIFIED: ImprovementActor.ETERNIAN,
        ImprovementState.HOLD: ImprovementActor.ETERNIAN,
        ImprovementState.BLOCKED: ImprovementActor.ETERNIAN,
        ImprovementState.FAILED: ImprovementActor.ETERNIAN,
    },
    ImprovementState.ETERNIAN_VERIFIED: {
        ImprovementState.CHANGE_REPORTED: ImprovementActor.ETERNIAN,
    },
    ImprovementState.CHANGE_REPORTED: {
        ImprovementState.DEPLOYMENT_APPROVAL_PENDING: ImprovementActor.OWNER,
        ImprovementState.HOLD: ImprovementActor.OWNER,
        ImprovementState.REJECTED: ImprovementActor.OWNER,
    },
}


def transition_improvement(
    request: SelfImprovementRequest,
    *,
    desired: ImprovementState,
    actor: ImprovementActor,
    expected_revision: int,
    now: datetime,
    owner_approval_digest: str | None = None,
    arkaon_verification_digest: str | None = None,
    eternian_audit_digest: str | None = None,
    eternian_remediation_digest: str | None = None,
) -> SelfImprovementRequest:
    if expected_revision != request.revision:
        raise ImprovementWorkflowError("IMPROVEMENT_REVISION_CONFLICT")
    if now.tzinfo is None or now < request.updated_at:
        raise ImprovementWorkflowError("CHRONOLOGICAL_TRANSITION_REQUIRED")
    required_actor = _ALLOWED_TRANSITIONS.get(request.state, {}).get(desired)
    if required_actor is None:
        raise ImprovementWorkflowError("IMPROVEMENT_TRANSITION_FORBIDDEN")
    if actor is not required_actor:
        raise ImprovementWorkflowError("IMPROVEMENT_ACTOR_FORBIDDEN")
    approval = request.owner_approval_digest
    if desired is ImprovementState.OWNER_APPROVED:
        if owner_approval_digest != request.scope_digest():
            raise ImprovementWorkflowError("OWNER_APPROVAL_SCOPE_DIGEST_REQUIRED")
        approval = owner_approval_digest
    if (
        desired is ImprovementState.SANDBOX_IMPLEMENTING
        and request.owner_approval_digest != request.scope_digest()
    ):
        raise ImprovementWorkflowError("OWNER_APPROVAL_REQUIRED_BEFORE_IMPLEMENTATION")
    verification = request.arkaon_verification_digest
    audit = request.eternian_audit_digest
    remediation = request.eternian_remediation_digest
    if desired is ImprovementState.ARKAON_VERIFIED:
        _require_evidence_digest(
            arkaon_verification_digest,
            "ARKAON_VERIFICATION_EVIDENCE_REQUIRED",
        )
        verification = arkaon_verification_digest
    if desired is ImprovementState.ETERNIAN_REMEDIATING:
        if request.owner_approval_digest != request.scope_digest():
            raise ImprovementWorkflowError("OWNER_APPROVAL_REQUIRED_BEFORE_REMEDIATION")
        _require_evidence_digest(eternian_audit_digest, "ETERNIAN_AUDIT_EVIDENCE_REQUIRED")
        audit = eternian_audit_digest
    if desired is ImprovementState.ETERNIAN_VERIFIED:
        if request.arkaon_verification_digest is None:
            raise ImprovementWorkflowError("ARKAON_VERIFICATION_REQUIRED_BEFORE_AUDIT")
        if request.state is ImprovementState.ETERNIAN_REMEDIATING:
            _require_evidence_digest(
                eternian_remediation_digest,
                "ETERNIAN_REMEDIATION_EVIDENCE_REQUIRED",
            )
            remediation = eternian_remediation_digest
        else:
            _require_evidence_digest(
                eternian_audit_digest,
                "ETERNIAN_AUDIT_EVIDENCE_REQUIRED",
            )
            audit = eternian_audit_digest
    return replace(
        request,
        state=desired,
        revision=request.revision + 1,
        updated_at=now,
        owner_approval_digest=approval,
        arkaon_verification_digest=verification,
        eternian_audit_digest=audit,
        eternian_remediation_digest=remediation,
    )


_EVIDENCE_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")


def _require_evidence_digest(value: str | None, code: str) -> None:
    if not isinstance(value, str) or _EVIDENCE_DIGEST.fullmatch(value) is None:
        raise ImprovementWorkflowError(code)


def post_self_improvement(
    request: SelfImprovementRequest,
    *,
    inbox_root: Path,
    now: datetime,
) -> tuple[SelfImprovementRequest, Path]:
    if request.state is not ImprovementState.DETECTED:
        raise ImprovementWorkflowError("DETECTED_REQUEST_REQUIRED")
    posted = transition_improvement(
        request,
        desired=ImprovementState.INBOX_POSTED,
        actor=ImprovementActor.ARKAON,
        expected_revision=request.revision,
        now=now,
    )
    stage = inbox_root / "self-improvement"
    stage.mkdir(parents=True, exist_ok=True)
    target = stage / f"{posted.request_id}.json"
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing.get("scope_digest") != posted.scope_digest():
            raise ImprovementWorkflowError("REQUEST_ID_SCOPE_CONFLICT")
        return posted, target
    target.write_text(
        json.dumps(posted.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return posted, target
