"""Fail-closed ARKAON GPU job policy and approval state machine. No provider credentials or network calls."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from secrets import token_urlsafe
from typing import Optional

class Provider(str, Enum):
    LOCAL = "local"
    RENTED = "rented"

class Status(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

@dataclass
class Job:
    id: str
    requester_id: str
    provider: Provider
    estimated_cost_krw: Decimal
    status: Status = Status.PENDING_APPROVAL
    approval_id: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    expires_at: Optional[str] = None
    cost_limit_krw: Optional[Decimal] = None
    dispatch_token: Optional[str] = None
    events: list[dict] = field(default_factory=list)

    def record(self, event: str, actor: str):
        self.events.append({"event": event, "actor": actor, "at": datetime.now(timezone.utc).isoformat()})

def submit(job_id: str, requester_id: str, provider: Provider, estimated_cost_krw: Decimal) -> Job:
    if not job_id or not requester_id or estimated_cost_krw < 0:
        raise ValueError("Invalid job")
    job = Job(job_id, requester_id, provider, estimated_cost_krw)
    job.record("submitted", requester_id)
    return job

def approve(job: Job, admin_id: str, approval_id: str, expires_at: str, cost_limit_krw: Decimal) -> None:
    if job.status != Status.PENDING_APPROVAL or not admin_id or not approval_id:
        raise PermissionError("Approval not allowed")
    if admin_id == job.requester_id:
        raise PermissionError("Separation of duties required")
    if cost_limit_krw < job.estimated_cost_krw:
        raise PermissionError("Insufficient budget approval")
    expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise PermissionError("Approval expired")
    # Caller must authenticate the administrator using server-side authorization.
    job.approved_by, job.approval_id, job.expires_at = admin_id, approval_id, expires_at
    job.approved_at, job.cost_limit_krw = datetime.now(timezone.utc).isoformat(), cost_limit_krw
    job.status = Status.APPROVED
    job.record("approved", admin_id)

def dispatch(job: Job, worker_provider: Provider, actor: str) -> str:
    if job.status != Status.APPROVED or not job.approval_id or not job.approved_by:
        raise PermissionError("Not approved")
    if job.provider != worker_provider:
        raise PermissionError("Provider mismatch")
    expiry = datetime.fromisoformat(job.expires_at.replace("Z", "+00:00"))
    if expiry <= datetime.now(timezone.utc) or job.cost_limit_krw is None or job.estimated_cost_krw > job.cost_limit_krw:
        raise PermissionError("Approval invalid or over budget")
    job.dispatch_token = token_urlsafe(32)
    job.status = Status.DISPATCHED
    job.record("dispatched", actor)
    return job.dispatch_token

def reject(job: Job, admin_id: str):
    if job.status != Status.PENDING_APPROVAL:
        raise PermissionError("Cannot reject")
    job.status = Status.REJECTED
    job.record("rejected", admin_id)
