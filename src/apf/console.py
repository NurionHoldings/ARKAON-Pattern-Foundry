import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .admin_change_control import AdminChangeController, ChangeControlRejected
from .durable_review import (
    DurableStoreError,
    ReviewAttestation,
    ReviewDecision,
    ReviewStage,
)
from .repository import TargetRepository

SESSION_COOKIE = "apf_console_session"
CSRF_COOKIE = "apf_console_csrf"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class ConsolePrincipal:
    tenant_id: UUID
    principal_id: UUID
    role: Literal["operator", "reviewer", "auditor"]


class DevSessionRequest(BaseModel):
    tenant_id: UUID
    principal_id: UUID
    role: Literal["operator", "reviewer", "auditor"] = "operator"


class OperatorApprovalRequest(BaseModel):
    scope_ids: list[str] = Field(min_length=1)
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeliveryApprovalRequest(BaseModel):
    approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class FulfillmentCompleteRequest(BaseModel):
    completion_note: str = Field(min_length=1, max_length=2000)


class ReviewSubmission(BaseModel):
    task_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    task_id: UUID
    job_id: UUID
    request_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    tenant_id: UUID
    principal_id: UUID
    stage: ReviewStage
    evidence_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision: ReviewDecision
    expires_at: datetime
    nonce: UUID
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    def attestation(self) -> ReviewAttestation:
        values = self.model_dump(mode="python")
        for key in ("task_id", "job_id", "tenant_id", "principal_id", "nonce"):
            values[key] = str(values[key])
        return ReviewAttestation(**values)


class ConsoleReviewStore(Protocol):
    def list_reviews_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int, offset: int,
    ): ...

    def get_review_for_principal(
        self, tenant_id: str, principal_id: str, task_id: str,
    ): ...

    def list_candidate_manifests_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int, offset: int,
    ): ...

    def decide_review(
        self, tenant_id: str, task_id: str, attestation: ReviewAttestation,
    ): ...


class ConsoleSecurity:
    def __init__(
        self, *, environment: str, secret: str | None, allow_dev_sessions: bool = False
    ) -> None:
        self.environment = environment.lower()
        self.secret = secret.encode() if secret else None
        self.allow_dev_sessions = allow_dev_sessions and self.environment not in {"production", "prod"}
        if self.environment in {"production", "prod"} and not self.secret:
            raise RuntimeError("APF_CONSOLE_SESSION_SECRET is required in production")

    def _signature(self, body: bytes) -> str:
        if not self.secret:
            raise HTTPException(status_code=503, detail="console authentication unavailable")
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def issue(self, principal: ConsolePrincipal) -> str:
        body = json.dumps(
            {
                "principal_id": str(principal.principal_id),
                "role": principal.role,
                "tenant_id": str(principal.tenant_id),
                "expires_at": int(time.time()) + 3600,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(body).decode().rstrip("=")
        return f"{encoded}.{self._signature(body)}"

    def verify(self, token: str | None) -> ConsolePrincipal:
        if not token or "." not in token:
            raise HTTPException(status_code=401, detail="console authentication required")
        encoded, signature = token.rsplit(".", 1)
        try:
            body = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            if not hmac.compare_digest(signature, self._signature(body)):
                raise ValueError
            value = json.loads(body)
            if not isinstance(value["expires_at"], int) or int(time.time()) >= value["expires_at"]:
                raise ValueError
            return ConsolePrincipal(
                tenant_id=UUID(value["tenant_id"]),
                principal_id=UUID(value["principal_id"]),
                role=value["role"],
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise HTTPException(status_code=401, detail="invalid console session") from None


def install_console(
    application, *, security: ConsoleSecurity, review_store: ConsoleReviewStore | None = None,
) -> None:
    application.state.console_security = security
    application.state.console_review_store = review_store

    def principal(
        request: Request,
        session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> ConsolePrincipal:
        return request.app.state.console_security.verify(session)

    def csrf_guard(
        request: Request,
        csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
        csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        if request.method not in SAFE_METHODS and (
            not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header)
        ):
            raise HTTPException(status_code=403, detail="CSRF verification failed")

    def repo(request: Request) -> TargetRepository:
        return request.app.state.repository

    def durable(request: Request) -> ConsoleReviewStore:
        store = request.app.state.console_review_store
        if store is None:
            raise HTTPException(status_code=503, detail="durable review store unavailable")
        return store

    def foundry_root() -> Path:
        return Path(__file__).parents[2]

    def change_controller() -> AdminChangeController:
        return AdminChangeController(foundry_root=foundry_root())

    def store_error(error: Exception) -> HTTPException:
        if isinstance(error, DurableStoreError):
            code = error.code
            if code in {"REVIEW_NOT_FOUND", "JOB_NOT_FOUND"}:
                return HTTPException(status_code=404, detail="review not found")
            if code in {"REVIEW_ALREADY_CLOSED", "REVIEW_NONCE_REPLAY"}:
                return HTTPException(status_code=409, detail=code)
            if code in {"REVIEW_EXPIRED", "REVIEW_ATTESTATION_EXPIRED"}:
                return HTTPException(status_code=422, detail=code)
            if code in {"REVIEW_BINDING_MISMATCH", "INVALID_REVIEW_SIGNATURE"}:
                return HTTPException(status_code=403, detail=code)
        return HTTPException(status_code=503, detail="durable review store unavailable")

    @application.post("/console/dev/session", include_in_schema=False)
    def create_dev_session(payload: DevSessionRequest, response: Response) -> dict[str, str]:
        if not security.allow_dev_sessions:
            raise HTTPException(status_code=404, detail="not found")
        token = security.issue(ConsolePrincipal(**payload.model_dump()))
        csrf = secrets.token_urlsafe(32)
        response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=True, samesite="strict")
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=True, samesite="strict")
        return {"csrf_token": csrf}

    @application.get("/console", response_class=HTMLResponse, include_in_schema=False)
    def console_home(actor: Annotated[ConsolePrincipal, Depends(principal)]) -> HTMLResponse:
        del actor
        html_path = Path(__file__).with_name("console_ui.html")
        return HTMLResponse(
            html_path.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get("/v1/console/map-ops-gate")
    def map_ops_gate_reports(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> list[dict[str, object]]:
        del actor
        store = foundry_root() / "state" / "map-ops-gate"
        if not store.is_dir():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(store.glob("*.json"), reverse=True)[:10]
        ]

    @application.get("/v1/console/plaza-governance")
    def plaza_governance_reports(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> list[dict[str, object]]:
        del actor
        store = foundry_root() / "state" / "plaza-governance"
        if not store.is_dir():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(store.glob("*.json"), reverse=True)[:10]
        ]

    @application.get("/v1/console/asset-investigation")
    def asset_investigation_reports(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        store = foundry_root() / "state" / "asset-investigation"
        if not store.is_dir():
            return {"priorities": [], "reports": []}
        reports = sorted(store.glob("*.json"), reverse=True)[:5]
        items = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        latest = items[0] if items else {}
        return {
            "catalog_revision": latest.get("catalog_revision"),
            "priorities": latest.get("priorities", []),
            "reports": items,
        }

    @application.get("/v1/console/capability-gaps")
    def capability_gap_reports(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        store = foundry_root() / "state" / "capability-gap"
        if not store.is_dir():
            return {"gap_count": 0, "reports": []}
        reports = sorted(store.glob("*.json"), reverse=True)[:10]
        items = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        latest = items[0] if items else {}
        gaps = latest.get("gaps") or []
        return {
            "owned_platform_id": latest.get("owned_platform_id"),
            "gap_count": latest.get("gap_count", len(gaps)),
            "gaps": gaps,
            "reports": items,
        }

    @application.get("/v1/console/pattern-promotion")
    def pattern_promotion_status(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        store = foundry_root() / "state" / "pattern-promotion"
        if not store.is_dir():
            return {
                "candidate_count": 30,
                "verified_count": 0,
                "pending_count": 30,
                "reuse_proof_ready": False,
                "reports": [],
            }
        reports = sorted(store.glob("*.json"), reverse=True)[:5]
        items = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        latest = items[0] if items else {}
        return {
            "candidate_count": latest.get("candidate_count", 30),
            "verified_count": latest.get("verified_count", 0),
            "pending_count": latest.get("pending_count", 30),
            "reuse_proof_ready": latest.get("reuse_proof") is not None,
            "catalog_revision": latest.get("catalog_revision"),
            "reports": items,
        }

    @application.get("/v1/console/predeployment")
    def predeployment_status(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        store = foundry_root() / "state" / "predeployment-readiness"
        if not store.is_dir():
            return {"overall": "UNKNOWN", "reports": []}
        reports = sorted(store.glob("*.json"), reverse=True)[:5]
        items = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        overall = items[0]["overall"] if items else "UNKNOWN"
        return {"overall": overall, "reports": items}

    @application.get("/v1/console/surface-observations")
    def surface_observations(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> list[dict[str, object]]:
        del actor
        store = foundry_root() / "state" / "surface-observations"
        if not store.is_dir():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(store.glob("*.json"), reverse=True)[:20]
        ]

    @application.get("/v1/console/inbox")
    def inbox_packets(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        stage: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[dict[str, object]]:
        del actor
        root = foundry_root() / "inbox"
        stages = [stage] if stage else ("research", "eternian-review", "operator-decision")
        items: list[dict[str, object]] = []
        for folder in stages:
            stage_dir = root / folder
            if not stage_dir.is_dir():
                continue
            for path in sorted(stage_dir.glob("*.json"))[:limit]:
                document = json.loads(path.read_text(encoding="utf-8"))
                items.append(
                    {
                        "packet_id": document.get("packet_id", path.stem),
                        "stage": document.get("stage", folder),
                        "platform_id": document.get("platform_id"),
                        "schema_version": document.get("schema_version"),
                        "summary": document.get("summary"),
                        "case_id": document.get("case_id"),
                        "proposal_id": document.get("proposal_id"),
                    }
                )
                if len(items) >= limit:
                    return items
        return items

    @application.get("/v1/console/mailbox")
    def mailbox_items(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        status: Annotated[str | None, Query()] = None,
    ) -> list[dict[str, object]]:
        del actor
        from .arkaon_mailbox import ArkaonMailbox, MailboxItemStatus

        mailbox = ArkaonMailbox(foundry_root=foundry_root())
        parsed = MailboxItemStatus(status) if status else None
        return [item.to_document() for item in mailbox.list_items(status=parsed)]

    @application.post("/v1/console/visitor/deliver")
    def visitor_deliver_to_user(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        from .arkaon_mailbox import ArkaonMailbox, MailboxRejected

        mailbox = ArkaonMailbox(foundry_root=foundry_root())
        visitor = ArkaonMailbox.visitor_for_console_role(actor.role, mailbox.policy)
        if visitor is None:
            raise HTTPException(
                status_code=403,
                detail="eternian(reviewer) or beom(operator) visitor role required",
            )
        try:
            message = mailbox.deliver_on_visitor_connect(
                visitor=visitor, now=datetime.now().astimezone(), recipient="user"
            )
        except MailboxRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        if message is None:
            return {"delivered": False, "message": "no pending mailbox items"}
        return {"delivered": True, **message.to_document()}

    @application.get("/v1/console/delivery-messages")
    def delivery_messages_for_user(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> list[dict[str, object]]:
        from .arkaon_mailbox import ArkaonMailbox

        mailbox = ArkaonMailbox(foundry_root=foundry_root())
        if actor.role != mailbox.policy.user_recipient_role:
            raise HTTPException(status_code=403, detail="user recipient role required")
        return [item.to_document() for item in mailbox.list_delivery_messages(limit=limit)]

    @application.post("/v1/console/delivery-messages/{message_id}/approve")
    def user_approve_delivery_message(
        message_id: str,
        payload: DeliveryApprovalRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .arkaon_mailbox import ArkaonMailbox, MailboxRejected

        mailbox = ArkaonMailbox(foundry_root=foundry_root())
        if actor.role != mailbox.policy.user_recipient_role:
            raise HTTPException(status_code=403, detail="user recipient role required")
        try:
            tasks = mailbox.user_approve_delivery(
                message_id=message_id,
                approval_digest=payload.approval_digest,
                now=datetime.now().astimezone(),
            )
        except MailboxRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return {
            "message_id": message_id,
            "fulfillment_tasks": [task.to_document() for task in tasks],
        }

    @application.post("/v1/console/delivery-messages/{message_id}/reject")
    def user_reject_delivery_message(
        message_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, str]:
        del csrf_verified
        from .arkaon_mailbox import ArkaonMailbox, MailboxRejected

        mailbox = ArkaonMailbox(foundry_root=foundry_root())
        if actor.role != mailbox.policy.user_recipient_role:
            raise HTTPException(status_code=403, detail="user recipient role required")
        try:
            mailbox.user_reject_delivery(message_id=message_id, now=datetime.now().astimezone())
        except MailboxRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return {"message_id": message_id, "status": "REJECTED"}

    @application.get("/v1/console/fulfillment-queue")
    def fulfillment_queue(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> list[dict[str, object]]:
        from .arkaon_mailbox import ArkaonMailbox

        mailbox = ArkaonMailbox(foundry_root=foundry_root())
        assignee = ArkaonMailbox.assignee_for_console_role(actor.role, mailbox.policy)
        if assignee is None:
            raise HTTPException(status_code=403, detail="eternian or beom role required")
        return [task.to_document() for task in mailbox.list_fulfillment_queue(assignee=assignee)]

    @application.post("/v1/console/fulfillment-queue/{task_id}/complete")
    def complete_fulfillment_task(
        task_id: str,
        payload: FulfillmentCompleteRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .arkaon_mailbox import ArkaonMailbox, MailboxRejected

        mailbox = ArkaonMailbox(foundry_root=foundry_root())
        assignee = ArkaonMailbox.assignee_for_console_role(actor.role, mailbox.policy)
        if assignee is None:
            raise HTTPException(status_code=403, detail="eternian or beom role required")
        tasks = mailbox.list_fulfillment_queue(assignee=assignee)
        if not any(task.task_id == task_id for task in tasks):
            raise HTTPException(status_code=404, detail="task not found for this assignee")
        try:
            completed = mailbox.complete_fulfillment(
                task_id=task_id,
                now=datetime.now().astimezone(),
                completion_note=payload.completion_note,
            )
        except MailboxRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return completed.to_document()

    @application.get("/v1/console/change-proposals")
    def change_proposals(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> list[dict[str, object]]:
        del actor
        controller = change_controller()
        return [
            {
                "proposal_id": item.proposal_id,
                "platform_id": item.platform_id,
                "case_id": item.case_id,
                "status": item.status.value,
                "summary": item.summary,
                "scope_ids": [scope.scope_id for scope in item.scopes],
            }
            for item in controller.list_proposals()
        ]

    @application.get("/v1/console/change-proposals/{proposal_id}")
    def change_proposal_detail(
        proposal_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        controller = change_controller()
        try:
            proposal = controller.get_proposal(proposal_id)
        except ChangeControlRejected as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        return proposal.to_document()

    @application.post("/v1/console/change-proposals/{proposal_id}/preview")
    def preview_change_proposal(
        proposal_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role not in {"operator", "reviewer"}:
            raise HTTPException(status_code=403, detail="operator or reviewer role required")
        controller = change_controller()
        try:
            preview = controller.preview(proposal_id)
        except ChangeControlRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return {
            "proposal_id": preview.proposal_id,
            "preview_digest": preview.preview_digest,
            "preview_only": preview.preview_only,
            "scope_previews": [
                {"scope_id": scope_id, "lines": list(lines)}
                for scope_id, lines in preview.scope_previews
            ],
        }

    @application.post("/v1/console/change-proposals/{proposal_id}/operator-approval")
    def approve_change_proposal(
        proposal_id: str,
        payload: OperatorApprovalRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, str]:
        del csrf_verified
        if actor.role != "operator":
            raise HTTPException(status_code=403, detail="operator role required")
        controller = change_controller()
        try:
            proposal = controller.get_proposal(proposal_id)
            if proposal.eternian_review_digest is None:
                raise ChangeControlRejected("eternian review digest required before operator approval")
            controller.operator_approve(
                proposal_id,
                scope_ids=tuple(payload.scope_ids),
                decision_digest=payload.decision_digest,
            )
        except ChangeControlRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return {"proposal_id": proposal_id, "status": "OPERATOR_APPROVED"}

    @application.post("/v1/console/change-proposals/{proposal_id}/partial-apply")
    def partial_apply_change_proposal(
        proposal_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "operator":
            raise HTTPException(status_code=403, detail="operator role required")
        controller = change_controller()
        try:
            record = controller.apply_partial(proposal_id, now=datetime.now().astimezone())
        except ChangeControlRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return {
            "proposal_id": record.proposal_id,
            "applied_scope_ids": list(record.applied_scope_ids),
            "apply_digest": record.apply_digest,
            "rollback_token": record.rollback_token,
            "intent_only": record.intent_only,
        }

    @application.get("/v1/console/summary")
    def summary(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        repository: Annotated[TargetRepository, Depends(repo)],
        request: Request,
    ) -> dict[str, object]:
        targets = repository.list_targets(actor.tenant_id)
        open_reviews = 0
        asset_candidates = 0
        store = request.app.state.console_review_store
        if store is not None:
            try:
                if hasattr(store, "count_reviews_for_principal"):
                    open_reviews = store.count_reviews_for_principal(
                        str(actor.tenant_id), str(actor.principal_id)
                    )
                if hasattr(store, "count_candidates_for_principal"):
                    asset_candidates = store.count_candidates_for_principal(
                        str(actor.tenant_id), str(actor.principal_id)
                    )
            except (DurableStoreError, sqlite3.Error, OSError):
                open_reviews = 0
                asset_candidates = 0
        readiness_path = Path(__file__).parents[2] / "knowledge/readiness/v0.1-readiness.json"
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        return {
            "principal": {"role": actor.role, "tenant_id": str(actor.tenant_id)},
            "counts": {
                "targets": len(targets),
                "open_reviews": open_reviews,
                "asset_candidates": asset_candidates,
            },
            "readiness": {
                "as_of_phase": readiness["as_of_phase"],
                "overall_status": readiness["overall_status"],
                "locks": readiness["locks"],
            },
        }

    @application.get("/v1/console/targets")
    def targets(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        repository: Annotated[TargetRepository, Depends(repo)],
    ) -> list[dict[str, object]]:
        return [
            {
                "id": str(item.id),
                "name": item.name,
                "type": item.target_type.value,
                "classification": item.classification.value,
                "state": item.state.value,
                "revision": item.revision,
                "evidence_count": len(item.source_evidence_ids),
            }
            for item in repository.list_targets(actor.tenant_id)
        ]

    @application.get("/console/api/reviews", include_in_schema=False)
    @application.get("/v1/console/reviews")
    def reviews(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConsoleReviewStore, Depends(durable)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, object]]:
        try:
            items = store.list_reviews_for_principal(
                str(actor.tenant_id), str(actor.principal_id), limit=limit, offset=offset
            )
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None
        return [{
            "task_id": item.task_id, "job_id": item.job_id, "stage": item.stage.value,
            "reason_code": item.reason_code, "evidence_fingerprint": item.evidence_fingerprint,
            "expires_at": item.expires_at.isoformat(), "status": item.status.value,
        } for item in items]

    @application.get("/v1/console/reviews/{task_id}")
    def review_detail(
        task_id: UUID,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConsoleReviewStore, Depends(durable)],
    ) -> dict[str, object]:
        try:
            item = store.get_review_for_principal(
                str(actor.tenant_id), str(actor.principal_id), str(task_id)
            )
        except (DurableStoreError, sqlite3.Error, OSError, AttributeError) as error:
            raise store_error(error) from None
        return {
            "task_id": item.task_id,
            "job_id": item.job_id,
            "stage": item.stage.value,
            "reason_code": item.reason_code,
            "evidence_fingerprint": item.evidence_fingerprint,
            "expires_at": item.expires_at.isoformat(),
            "status": item.status.value,
            "request_fingerprint": item.request_fingerprint,
        }

    @application.get("/console/api/candidates", include_in_schema=False)
    @application.get("/v1/console/candidates")
    def candidates(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConsoleReviewStore, Depends(durable)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, object]]:
        try:
            return list(store.list_candidate_manifests_for_principal(
                str(actor.tenant_id), str(actor.principal_id), limit=limit, offset=offset
            ))
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None

    @application.get("/v1/console/candidates/{job_id}")
    def candidate_detail(
        job_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConsoleReviewStore, Depends(durable)],
    ) -> dict[str, object]:
        try:
            items = store.list_candidate_manifests_for_principal(
                str(actor.tenant_id), str(actor.principal_id), limit=100, offset=0
            )
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None
        for item in items:
            if item.get("job_id") == job_id or item.get("job_fingerprint", "").endswith(job_id):
                return item
        raise HTTPException(status_code=404, detail="candidate not found")

    @application.get("/v1/console/postgres-live-proof")
    def postgres_live_proof_status(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        store = foundry_root() / "state" / "postgres-live-proof"
        if not store.is_dir():
            return {"overall": "UNKNOWN", "reports": []}
        reports = sorted(store.glob("*.json"), reverse=True)[:5]
        items = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        overall = items[0]["overall"] if items else "UNKNOWN"
        return {"overall": overall, "reports": items}

    @application.get("/v1/console/owned-platform-live")
    def owned_platform_live_status(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        store = foundry_root() / "state" / "owned-platform-live"
        if not store.is_dir():
            return {"overall": "UNKNOWN", "reports": []}
        reports = sorted(store.glob("*.json"), reverse=True)[:5]
        items = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        overall = items[0]["overall"] if items else "UNKNOWN"
        return {"overall": overall, "reports": items}

    @application.get("/v1/console/reuse-proof-measurement")
    def reuse_proof_measurement_status(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        store = foundry_root() / "state" / "reuse-proof-measurement"
        if not store.is_dir():
            return {"overall": "UNKNOWN", "reports": []}
        reports = sorted(store.glob("*.json"), reverse=True)[:5]
        items = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        overall = items[0]["overall"] if items else "UNKNOWN"
        return {"overall": overall, "reports": items}

    @application.post(
        "/console/api/reviews/{task_id}/decisions", status_code=status.HTTP_202_ACCEPTED,
        include_in_schema=False,
    )
    @application.post("/v1/console/reviews/{task_id}/decisions", status_code=status.HTTP_202_ACCEPTED)
    def submit_review(
        task_id: UUID,
        payload: ReviewSubmission,
        request: Request,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, str]:
        del csrf_verified
        if actor.role != "reviewer":
            raise HTTPException(status_code=403, detail="reviewer role required")
        store = durable(request)
        if (payload.task_id != task_id or payload.tenant_id != actor.tenant_id
                or payload.principal_id != actor.principal_id):
            raise HTTPException(status_code=403, detail="review binding mismatch")
        try:
            decided = store.decide_review(str(actor.tenant_id), str(task_id), payload.attestation())
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None
        return {"task_id": decided.task_id, "decision": payload.decision.value,
                "status": decided.status.value}


def console_security_from_config(
    *, environment: str | None = None, secret: str | None = None
) -> ConsoleSecurity:
    return ConsoleSecurity(
        environment=environment or os.getenv("APF_ENV", "development"),
        secret=secret or os.getenv("APF_CONSOLE_SESSION_SECRET"),
        allow_dev_sessions=os.getenv("APF_ENABLE_DEV_SESSION", "").lower() == "true",
    )
