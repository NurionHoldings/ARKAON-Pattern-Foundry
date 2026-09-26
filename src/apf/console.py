import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .admin_change_control import AdminChangeController, ChangeControlRejected
from .business_card import (
    BusinessCardError,
    BusinessCardRequest,
    BusinessCardRevisionRequest,
    BusinessCardRollbackRequest,
    BusinessCardStore,
)
from .conversational_site_draft import (
    ConversationalSiteDraftStore,
    SiteDraftError,
    SiteDraftRequest,
    SiteDraftRevisionRequest,
)
from .durable_review import (
    DurableStoreError,
    ReviewAttestation,
    ReviewDecision,
    ReviewStage,
)
from .logo_draft import (
    LogoDraftError,
    LogoDraftRequest,
    LogoDraftStore,
    LogoRevisionRequest,
    LogoRollbackRequest,
)
from .plain_language_approval import (
    ApprovalDecision,
    PlainApprovalError,
    PlainLanguageApprovalStore,
)
from .reference_material_consent import (
    NOTICE_TEXT,
    NOTICE_VERSION,
    REQUIRED_ACKNOWLEDGEMENTS,
    ReferenceConsentError,
    ReferenceConsentStore,
    ReferenceUseConsent,
    ReferenceUseRequest,
)
from .reference_material_consent import (
    digest as reference_digest,
)
from .repository import TargetRepository
from .visual_platform_dialogue import (
    PlatformBrief,
    RevisionFeedback,
    RevisionSubmission,
    UnderstandingConfirmation,
    VisualDialogueError,
    VisualPlatformDialogueStore,
)

SESSION_COOKIE = "apf_console_session"
CSRF_COOKIE = "apf_console_csrf"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class ConsolePrincipal:
    tenant_id: UUID
    principal_id: UUID
    role: Literal["owner", "operator", "reviewer", "auditor"]


class DevSessionRequest(BaseModel):
    tenant_id: UUID
    principal_id: UUID
    role: Literal["owner", "operator", "reviewer", "auditor"] = "operator"


class OperatorApprovalRequest(BaseModel):
    scope_ids: list[str] = Field(min_length=1)
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeliveryApprovalRequest(BaseModel):
    approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class FulfillmentCompleteRequest(BaseModel):
    completion_note: str = Field(min_length=1, max_length=2000)


class CoCreationChatRequest(BaseModel):
    session_id: str | None = None
    platform_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    scope: Literal["TEMPLATE", "PLATFORM", "BOTH"] = "BOTH"
    payment_entitlement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_site_url: str | None = Field(default=None, max_length=512)
    feature_reference_urls: dict[str, str] | None = None


class CoCreationBuildRequest(BaseModel):
    proposal_id: str = Field(min_length=8, max_length=64)
    operator_approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoCreationCodegenRequest(BaseModel):
    proposal_id: str = Field(min_length=8, max_length=64)
    operator_approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoCreationCodegenApproveRequest(BaseModel):
    operator_codegen_approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoCreationPreviewStartRequest(BaseModel):
    proposal_id: str = Field(min_length=8, max_length=64)
    platform_id: str = Field(min_length=1, max_length=128)
    preview_base_url: str = Field(min_length=8, max_length=512)
    payment_entitlement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoCreationPreviewFeedbackRequest(BaseModel):
    platform_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    payment_entitlement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProposalQualityReplenishRequest(BaseModel):
    platform_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    user_dissatisfied: bool = False


class CoCreationPreviewAcceptRequest(BaseModel):
    platform_id: str = Field(min_length=1, max_length=128)
    payment_entitlement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoCreationDeployShadowRequest(BaseModel):
    proposal_id: str = Field(min_length=8, max_length=64)
    platform_id: str = Field(min_length=1, max_length=128)
    codegen_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operator_approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sandbox_id: str | None = None


class CoCreationDeployPromoteRequest(BaseModel):
    stage: Literal["PILOT", "PRODUCTION"]
    operator_approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    eternian_approval_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    eternian_principal_id: UUID | None = None


class CoCreationDeployKillRequest(BaseModel):
    operator_approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class SelfEvolutionProposeToUserRequest(BaseModel):
    platform_id: str = Field(min_length=1, max_length=128)
    payment_entitlement_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    baseline_snapshot_id: str | None = None
    candidate_snapshot_id: str | None = None


class GitHubOnboardingRequest(BaseModel):
    platform_id: str = Field(min_length=1, max_length=128)
    console_base_url: str = Field(min_length=8, max_length=512)
    github_client_id: str | None = None


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


class ReferenceConsentSubmission(BaseModel):
    request: ReferenceUseRequest
    acknowledged_items: set[str]
    nonce: UUID


class ConsoleReviewStore(Protocol):
    def list_reviews_for_principal(
        self,
        tenant_id: str,
        principal_id: str,
        *,
        limit: int,
        offset: int,
    ): ...

    def get_review_for_principal(
        self, tenant_id: str, principal_id: str, task_id: str,
    ): ...

    def list_candidate_manifests_for_principal(
        self,
        tenant_id: str,
        principal_id: str,
        *,
        limit: int,
        offset: int,
    ): ...

    def decide_review(
        self,
        tenant_id: str,
        task_id: str,
        attestation: ReviewAttestation,
    ): ...


class ConsoleSecurity:
    def __init__(
        self, *, environment: str, secret: str | None, allow_dev_sessions: bool = False
    ) -> None:
        self.environment = environment.lower()
        self.secret = secret.encode() if secret else None
        self.allow_dev_sessions = allow_dev_sessions and self.environment not in {
            "production",
            "prod",
        }
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
    application,
    *,
    security: ConsoleSecurity,
    review_store: ConsoleReviewStore | None = None,
    approval_store: PlainLanguageApprovalStore | None = None,
    visual_dialogue_store: VisualPlatformDialogueStore | None = None,
    conversational_site_draft_store: ConversationalSiteDraftStore | None = None,
    logo_draft_store: LogoDraftStore | None = None,
    business_card_store: BusinessCardStore | None = None,
    reference_consent_store: ReferenceConsentStore | None = None,
) -> None:
    application.state.console_security = security
    application.state.console_review_store = review_store
    application.state.plain_approval_store = approval_store
    application.state.visual_dialogue_store = visual_dialogue_store
    application.state.conversational_site_draft_store = conversational_site_draft_store
    application.state.logo_draft_store = logo_draft_store
    application.state.business_card_store = business_card_store
    application.state.reference_consent_store = reference_consent_store

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
    def approvals(request: Request) -> PlainLanguageApprovalStore:
        store = request.app.state.plain_approval_store
        if store is None:
            raise HTTPException(status_code=503, detail="plain-language approval store unavailable")
        return store

    def visual_dialogues(request: Request) -> VisualPlatformDialogueStore:
        store = request.app.state.visual_dialogue_store
        if store is None:
            raise HTTPException(status_code=503, detail="visual dialogue store unavailable")
        return store

    def site_drafts(request: Request) -> ConversationalSiteDraftStore:
        store = request.app.state.conversational_site_draft_store
        if store is None:
            raise HTTPException(
                status_code=503, detail="conversational site draft store unavailable"
            )
        return store

    def logo_drafts(request: Request) -> LogoDraftStore:
        store = request.app.state.logo_draft_store
        if store is None:
            raise HTTPException(status_code=503, detail="logo draft store unavailable")
        return store

    def business_cards(request: Request) -> BusinessCardStore:
        store = request.app.state.business_card_store
        if store is None:
            raise HTTPException(status_code=503, detail="business card store unavailable")
        return store

    def reference_consents(request: Request) -> ReferenceConsentStore:
        store = request.app.state.reference_consent_store
        if store is None:
            raise HTTPException(status_code=503, detail="reference consent store unavailable")
        return store

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
        stage: Annotated[Literal["research", "eternian-review", "operator-decision"] | None, Query()] = None,
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

    @application.get("/v1/console/co-creation/proposals")
    def co_creation_proposals(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> list[dict[str, object]]:
        del actor
        store = foundry_root() / "state" / "co-creation" / "proposals"
        if not store.is_dir():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(store.glob("*.json"), reverse=True)[:limit]
        ]

    @application.get("/v1/console/co-creation/sessions/{session_id}")
    def co_creation_session(
        session_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        try:
            safe_session_id = str(UUID(session_id))
        except ValueError:
            raise HTTPException(status_code=404, detail="session not found") from None
        path = foundry_root() / "state" / "co-creation" / "sessions" / f"{safe_session_id}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="session not found")
        document = json.loads(path.read_text(encoding="utf-8"))
        if (document.get("tenant_id") != str(actor.tenant_id)
                or document.get("principal_id") != str(actor.principal_id)):
            raise HTTPException(status_code=404, detail="session not found")
        return document

    @application.post("/v1/console/co-creation/chat")
    def co_creation_chat(
        payload: CoCreationChatRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .conversational_co_creation import (
            CoCreationRejected,
            CoCreationScope,
            ConversationalCoCreationEngine,
        )
        from .conversational_co_creation_bridge import bridge_co_creation_proposal

        engine = ConversationalCoCreationEngine(foundry_root=foundry_root())
        now = datetime.now().astimezone()
        try:
            proposal = engine.chat(
                tenant_id=str(actor.tenant_id),
                principal_id=str(actor.principal_id),
                platform_id=payload.platform_id,
                message=payload.message,
                scope=CoCreationScope(payload.scope),
                payment_entitlement_digest=payload.payment_entitlement_digest,
                now=now,
                session_id=payload.session_id,
                reference_site_url=payload.reference_site_url,
                feature_reference_urls=payload.feature_reference_urls,
            )
        except CoCreationRejected as error:
            status = 402 if error.code == "PAYMENT_REQUIRED" else 422
            if error.code in {"INSUFFICIENT_EXPERIENCE", "INSUFFICIENT_PROPOSAL_QUALITY"}:
                status = 409
            raise HTTPException(status_code=status, detail=error.code) from None
        bridge_co_creation_proposal(
            foundry_root=foundry_root(),
            proposal=proposal,
            policy=engine.policy,
            run_id=proposal.proposal_id,
            now=now,
            dry_run=False,
        )
        document = proposal.to_document()
        return {
            "session_id": proposal.session_id,
            "proposal_id": proposal.proposal_id,
            "assistant_reply": proposal.assistant_reply,
            "scope": proposal.scope.value,
            "recommended_structure": document["recommended_structure"],
            "template_blueprint": document["template_blueprint"],
            "platform_blueprint": document["platform_blueprint"],
            "evidence_table": document["evidence_table"],
            "copy_angle_options": document["copy_angle_options"],
            "reference_site_url": proposal.reference_site_url,
            "reference_style_path": proposal.reference_style_path,
            "feature_reference_styles": document["feature_reference_styles"],
            "proposal_quality_score_at_intake": proposal.proposal_quality_score_at_intake,
            "proposal_quality_replenished": proposal.proposal_quality_replenished,
            "proposal_quality_replenish_trigger": proposal.proposal_quality_replenish_trigger,
            "proposal_quality_replenish_digest": proposal.proposal_quality_replenish_digest,
        }

    @application.post("/v1/console/co-creation/build")
    def co_creation_build_after_approval(
        payload: CoCreationBuildRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .co_creation_build import CoCreationBuildEngine, CoCreationBuildRejected

        engine = CoCreationBuildEngine(foundry_root=foundry_root())
        try:
            report = engine.build_after_approval(
                proposal_id=payload.proposal_id,
                operator_approval_digest=payload.operator_approval_digest,
                now=datetime.now().astimezone(),
            )
        except CoCreationBuildRejected as error:
            raise HTTPException(status_code=422, detail=error.code) from None
        return report.to_document()

    @application.post("/v1/console/co-creation/codegen")
    def co_creation_codegen(
        payload: CoCreationCodegenRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified, actor
        from .co_creation_codegen import CoCreationCodegenEngine, CoCreationCodegenRejected
        from .co_creation_codegen_bridge import bridge_codegen_manifest

        engine = CoCreationCodegenEngine(foundry_root=foundry_root())
        now = datetime.now().astimezone()
        try:
            manifest = engine.run_codegen(
                proposal_id=payload.proposal_id,
                operator_approval_digest=payload.operator_approval_digest,
                now=now,
            )
        except CoCreationCodegenRejected as error:
            status = 422
            if error.code == "CONTAMINATION_BLOCKED":
                status = 409
            raise HTTPException(status_code=status, detail=error.code) from None
        bridge_codegen_manifest(
            foundry_root=foundry_root(),
            manifest=manifest,
            policy=engine.policy,
            run_id=manifest.proposal_id,
            now=now,
            dry_run=False,
        )
        return manifest.to_document()

    @application.get("/v1/console/co-creation/codegen/{proposal_id}")
    def co_creation_codegen_manifest(
        proposal_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        from .co_creation_codegen import CoCreationCodegenEngine, CoCreationCodegenRejected

        engine = CoCreationCodegenEngine(foundry_root=foundry_root())
        try:
            manifest = engine.load_manifest(proposal_id)
        except CoCreationCodegenRejected as error:
            raise HTTPException(status_code=404, detail=error.code) from None
        return manifest.to_document()

    @application.post("/v1/console/co-creation/codegen/{proposal_id}/approve")
    def co_creation_codegen_approve(
        proposal_id: str,
        payload: CoCreationCodegenApproveRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified, actor
        from .co_creation_codegen import CoCreationCodegenEngine, CoCreationCodegenRejected

        engine = CoCreationCodegenEngine(foundry_root=foundry_root())
        try:
            manifest = engine.approve_codegen(
                proposal_id=proposal_id,
                operator_codegen_approval_digest=payload.operator_codegen_approval_digest,
                now=datetime.now().astimezone(),
            )
        except CoCreationCodegenRejected as error:
            raise HTTPException(status_code=422, detail=error.code) from None
        return manifest.to_document()

    @application.post("/v1/console/co-creation/preview/start")
    def co_creation_preview_start(
        payload: CoCreationPreviewStartRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .co_creation_preview import CoCreationPreviewEngine, CoCreationPreviewRejected

        engine = CoCreationPreviewEngine(foundry_root=foundry_root())
        try:
            runtime = engine.start_preview(
                proposal_id=payload.proposal_id,
                tenant_id=str(actor.tenant_id),
                principal_id=str(actor.principal_id),
                platform_id=payload.platform_id,
                preview_base_url=payload.preview_base_url,
                payment_entitlement_digest=payload.payment_entitlement_digest,
                now=datetime.now().astimezone(),
            )
        except CoCreationPreviewRejected as error:
            status = 422
            if error.code in {"ENTITLEMENT_INACTIVE", "TENANT_FORBIDDEN"}:
                status = 403
            if error.code == "CODEGEN_NOT_READY":
                status = 409
            raise HTTPException(status_code=status, detail=error.code) from None
        return runtime.to_document()

    @application.get("/v1/console/co-creation/preview/{sandbox_id}")
    def co_creation_preview_get(
        sandbox_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        platform_id: Annotated[str, Query(min_length=1, max_length=128)],
        payment_entitlement_digest: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
    ) -> dict[str, object]:
        from .co_creation_preview import CoCreationPreviewEngine, CoCreationPreviewRejected

        engine = CoCreationPreviewEngine(foundry_root=foundry_root())
        try:
            runtime = engine.get_sandbox(
                sandbox_id=sandbox_id,
                tenant_id=str(actor.tenant_id),
                principal_id=str(actor.principal_id),
                platform_id=platform_id,
                payment_entitlement_digest=payment_entitlement_digest,
                now=datetime.now().astimezone(),
            )
        except CoCreationPreviewRejected as error:
            status = 404
            if error.code in {"ENTITLEMENT_INACTIVE", "TENANT_FORBIDDEN"}:
                status = 403
            if error.code == "SANDBOX_EXPIRED":
                status = 410
            raise HTTPException(status_code=status, detail=error.code) from None
        return runtime.to_document()

    @application.delete("/v1/console/co-creation/preview/{sandbox_id}")
    def co_creation_preview_teardown(
        sandbox_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .co_creation_preview import CoCreationPreviewEngine, CoCreationPreviewRejected

        engine = CoCreationPreviewEngine(foundry_root=foundry_root())
        try:
            runtime = engine.teardown(
                sandbox_id=sandbox_id,
                tenant_id=str(actor.tenant_id),
                now=datetime.now().astimezone(),
            )
        except CoCreationPreviewRejected as error:
            status = 404 if error.code == "SANDBOX_NOT_FOUND" else 403
            raise HTTPException(status_code=status, detail=error.code) from None
        return runtime.to_document()

    @application.post("/v1/console/co-creation/preview/{sandbox_id}/feedback")
    def co_creation_preview_feedback(
        sandbox_id: str,
        payload: CoCreationPreviewFeedbackRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .co_creation_preview import CoCreationPreviewEngine, CoCreationPreviewRejected

        engine = CoCreationPreviewEngine(foundry_root=foundry_root())
        try:
            runtime, proposal_id, loop_result = engine.submit_feedback(
                sandbox_id=sandbox_id,
                tenant_id=str(actor.tenant_id),
                principal_id=str(actor.principal_id),
                platform_id=payload.platform_id,
                message=payload.message,
                payment_entitlement_digest=payload.payment_entitlement_digest,
                now=datetime.now().astimezone(),
            )
        except CoCreationPreviewRejected as error:
            status = 422
            if error.code in {"ENTITLEMENT_INACTIVE", "TENANT_FORBIDDEN", "SANDBOX_EXPIRED"}:
                status = 403 if error.code != "SANDBOX_EXPIRED" else 410
            if error.code in {"INSUFFICIENT_EXPERIENCE", "INSUFFICIENT_PROPOSAL_QUALITY", "REVISION_LIMIT"}:
                status = 409
            raise HTTPException(status_code=status, detail=error.code) from None
        document = runtime.to_document()
        document["revision_proposal_id"] = proposal_id
        document["feedback_loop"] = loop_result
        if loop_result and loop_result.get("proposal_quality_replenish"):
            document["proposal_quality_replenish"] = loop_result["proposal_quality_replenish"]
        return document

    @application.post("/v1/console/co-creation/preview/{sandbox_id}/accept")
    def co_creation_preview_accept(
        sandbox_id: str,
        payload: CoCreationPreviewAcceptRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .co_creation_preview import CoCreationPreviewEngine, CoCreationPreviewRejected

        engine = CoCreationPreviewEngine(foundry_root=foundry_root())
        try:
            runtime = engine.accept_preview(
                sandbox_id=sandbox_id,
                tenant_id=str(actor.tenant_id),
                principal_id=str(actor.principal_id),
                platform_id=payload.platform_id,
                payment_entitlement_digest=payload.payment_entitlement_digest,
                now=datetime.now().astimezone(),
            )
        except CoCreationPreviewRejected as error:
            status = 403 if error.code in {"ENTITLEMENT_INACTIVE", "TENANT_FORBIDDEN"} else 422
            raise HTTPException(status_code=status, detail=error.code) from None
        return runtime.to_document()

    @application.get("/v1/console/co-creation/feedback-loop/{session_id}")
    def co_creation_feedback_loop_state(
        session_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        from .co_creation_feedback_loop import CoCreationFeedbackLoopEngine

        engine = CoCreationFeedbackLoopEngine(foundry_root=foundry_root())
        state = engine._load_loop_state(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="FEEDBACK_LOOP_NOT_FOUND")
        return state.to_document()

    @application.post("/v1/console/co-creation/deploy/shadow")
    def co_creation_deploy_shadow(
        payload: CoCreationDeployShadowRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .co_creation_deploy import CoCreationDeployEngine, CoCreationDeployRejected

        engine = CoCreationDeployEngine(foundry_root=foundry_root())
        try:
            state = engine.start_shadow(
                proposal_id=payload.proposal_id,
                tenant_id=str(actor.tenant_id),
                platform_id=payload.platform_id,
                sandbox_id=payload.sandbox_id,
                codegen_manifest_digest=payload.codegen_manifest_digest,
                operator_approval_digest=payload.operator_approval_digest,
                operator_principal_id=str(actor.principal_id),
                now=datetime.now().astimezone(),
            )
        except CoCreationDeployRejected as error:
            status = 422
            if error.code == "PREDEPLOY_FAILED":
                status = 409
            raise HTTPException(status_code=status, detail=error.code) from None
        return state.to_document()

    @application.post("/v1/console/co-creation/deploy/{proposal_id}/promote")
    def co_creation_deploy_promote(
        proposal_id: str,
        payload: CoCreationDeployPromoteRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .co_creation_deploy import (
            CoCreationDeployEngine,
            CoCreationDeployRejected,
            DeployRolloutStage,
        )

        engine = CoCreationDeployEngine(foundry_root=foundry_root())
        try:
            state = engine.promote(
                proposal_id=proposal_id,
                stage=DeployRolloutStage(payload.stage),
                operator_approval_digest=payload.operator_approval_digest,
                eternian_approval_digest=payload.eternian_approval_digest,
                operator_principal_id=str(actor.principal_id),
                eternian_principal_id=(
                    str(payload.eternian_principal_id) if payload.eternian_principal_id else None
                ),
                now=datetime.now().astimezone(),
            )
        except CoCreationDeployRejected as error:
            status = 422
            if error.code in {"PRODUCTION_LOCKED", "PREDEPLOY_FAILED", "STAGE_ORDER"}:
                status = 409
            if error.code == "DUAL_APPROVAL_FORBIDDEN":
                status = 403
            raise HTTPException(status_code=status, detail=error.code) from None
        return state.to_document()

    @application.post("/v1/console/co-creation/deploy/{proposal_id}/kill")
    def co_creation_deploy_kill(
        proposal_id: str,
        payload: CoCreationDeployKillRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified, actor
        from .co_creation_deploy import CoCreationDeployEngine, CoCreationDeployRejected

        engine = CoCreationDeployEngine(foundry_root=foundry_root())
        try:
            state = engine.kill_switch(
                proposal_id=proposal_id,
                operator_approval_digest=payload.operator_approval_digest,
                now=datetime.now().astimezone(),
            )
        except CoCreationDeployRejected as error:
            raise HTTPException(status_code=422, detail=error.code) from None
        return state.to_document()

    @application.get("/v1/console/co-creation/deploy/{proposal_id}")
    def co_creation_deploy_status(
        proposal_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        from .co_creation_deploy import CoCreationDeployEngine, CoCreationDeployRejected

        engine = CoCreationDeployEngine(foundry_root=foundry_root())
        try:
            state = engine.get_status(proposal_id)
        except CoCreationDeployRejected as error:
            raise HTTPException(status_code=404, detail=error.code) from None
        return state.to_document()

    @application.get("/v1/console/proposal-quality")
    def proposal_quality_latest(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        del actor
        from .proposal_quality_score import ProposalQualityScorer

        scorer = ProposalQualityScorer(foundry_root=foundry_root())
        latest = scorer.load_latest()
        if latest is None:
            report = scorer.evaluate_and_persist(now=datetime.now().astimezone())
            return report.to_document()
        return latest.to_document()

    @application.get("/v1/console/proposal-quality/replenish")
    def proposal_quality_replenish_list(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> list[dict[str, object]]:
        del actor
        from .proposal_quality_replenish import ProposalQualityReplenishEngine

        engine = ProposalQualityReplenishEngine(foundry_root=foundry_root())
        return [item.to_document() for item in engine.list_recent(limit=limit)]

    @application.post("/v1/console/proposal-quality/replenish")
    def proposal_quality_replenish_run(
        payload: ProposalQualityReplenishRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified, actor
        from .proposal_quality_replenish import (
            ProposalQualityReplenishEngine,
            ProposalQualityReplenishRejected,
            user_dissatisfaction_detected,
        )
        from .proposal_quality_score import (
            ProposalQualityRejected,
            ProposalQualityScorer,
            assert_proposal_quality_gate,
        )

        now = datetime.now().astimezone()
        engine = ProposalQualityReplenishEngine(foundry_root=foundry_root())
        user_dissatisfied = payload.user_dissatisfied or user_dissatisfaction_detected(payload.message)
        before = ProposalQualityScorer(foundry_root=foundry_root()).evaluate(now=now)
        trigger, should = engine._decide_replenish(before, user_dissatisfied=user_dissatisfied)
        if not should:
            return {
                "replenished": False,
                "reason": "NO_REPLENISH_TRIGGER",
                "proposal_quality": before.to_document(),
            }
        try:
            report = engine.replenish(
                platform_id=payload.platform_id,
                message=payload.message,
                trigger=trigger,
                now=now,
            )
        except ProposalQualityReplenishRejected as error:
            raise HTTPException(status_code=422, detail=error.code) from None
        try:
            quality = assert_proposal_quality_gate(foundry_root=foundry_root())
        except ProposalQualityRejected:
            quality = ProposalQualityScorer(foundry_root=foundry_root()).evaluate(now=now)
        return {
            "replenished": True,
            "replenish_report": report.to_document(),
            "proposal_quality": quality.to_document(),
        }

    @application.get("/v1/console/self-evolution/snapshots")
    def self_evolution_snapshots(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> list[dict[str, object]]:
        del actor
        from .arkaon_self_evolution_compare import ArkaonSelfEvolutionCompareEngine

        engine = ArkaonSelfEvolutionCompareEngine(foundry_root=foundry_root())
        return [item.to_document() for item in engine.list_snapshots(limit=limit)]

    @application.get("/v1/console/self-evolution/compare")
    def self_evolution_compare(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        baseline_snapshot_id: Annotated[str | None, Query()] = None,
        candidate_snapshot_id: Annotated[str | None, Query()] = None,
        include_analysis: Annotated[bool, Query()] = False,
    ) -> dict[str, object]:
        del actor
        from .arkaon_self_evolution_analysis import (
            ArkaonSelfEvolutionAnalysisEngine,
            SelfEvolutionAnalysisRejected,
        )
        from .arkaon_self_evolution_compare import (
            ArkaonSelfEvolutionCompareEngine,
            SelfEvolutionRejected,
        )

        engine = ArkaonSelfEvolutionCompareEngine(foundry_root=foundry_root())
        now = datetime.now().astimezone()
        try:
            if baseline_snapshot_id and candidate_snapshot_id:
                report = engine.compare(
                    baseline_snapshot_id=baseline_snapshot_id,
                    candidate_snapshot_id=candidate_snapshot_id,
                    now=now,
                )
            else:
                report = engine.compare_latest_pair(now=now)
        except SelfEvolutionRejected as error:
            raise HTTPException(status_code=404, detail=error.code) from None
        document = report.to_document()
        if include_analysis:
            try:
                analysis_engine = ArkaonSelfEvolutionAnalysisEngine(foundry_root=foundry_root())
                analysis = analysis_engine.analyze_comparison(report=report, now=now)
                document["improvement_analysis"] = analysis.to_document()
            except SelfEvolutionAnalysisRejected as error:
                raise HTTPException(status_code=422, detail=error.code) from None
        return document

    @application.get("/v1/console/self-evolution/analyze")
    def self_evolution_analyze(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        baseline_snapshot_id: Annotated[str | None, Query()] = None,
        candidate_snapshot_id: Annotated[str | None, Query()] = None,
    ) -> dict[str, object]:
        del actor
        from .arkaon_self_evolution_analysis import (
            ArkaonSelfEvolutionAnalysisEngine,
            SelfEvolutionAnalysisRejected,
        )

        engine = ArkaonSelfEvolutionAnalysisEngine(foundry_root=foundry_root())
        now = datetime.now().astimezone()
        try:
            if baseline_snapshot_id and candidate_snapshot_id:
                analysis = engine.analyze(
                    baseline_snapshot_id=baseline_snapshot_id,
                    candidate_snapshot_id=candidate_snapshot_id,
                    now=now,
                )
            else:
                analysis = engine.analyze_latest(now=now)
        except SelfEvolutionAnalysisRejected as error:
            raise HTTPException(status_code=404, detail=error.code) from None
        return analysis.to_document()

    @application.post("/v1/console/self-evolution/propose-to-user")
    def self_evolution_propose_to_user(
        payload: SelfEvolutionProposeToUserRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .arkaon_user_feature_proposal import (
            ArkaonUserFeatureProposalEngine,
            UserFeatureProposalRejected,
        )

        engine = ArkaonUserFeatureProposalEngine(foundry_root=foundry_root())
        try:
            proposal = engine.propose_to_user(
                tenant_id=str(actor.tenant_id),
                principal_id=str(actor.principal_id),
                platform_id=payload.platform_id,
                payment_entitlement_digest=payload.payment_entitlement_digest,
                now=datetime.now().astimezone(),
                analysis_digest=payload.analysis_digest,
                baseline_snapshot_id=payload.baseline_snapshot_id,
                candidate_snapshot_id=payload.candidate_snapshot_id,
            )
        except UserFeatureProposalRejected as error:
            status = 403 if error.code == "ENTITLEMENT_INACTIVE" else 422
            if error.code == "INSUFFICIENT_HISTORY":
                status = 409
            raise HTTPException(status_code=status, detail=error.code) from None
        return proposal.to_document()

    @application.get("/v1/console/self-evolution/user-proposals")
    def self_evolution_user_proposals(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> list[dict[str, object]]:
        from .arkaon_user_feature_proposal import ArkaonUserFeatureProposalEngine

        engine = ArkaonUserFeatureProposalEngine(foundry_root=foundry_root())
        return [
            item.to_document()
            for item in engine.list_proposals(tenant_id=str(actor.tenant_id), limit=limit)
        ]

    @application.post("/v1/console/co-creation/github-onboarding/start")
    def co_creation_github_onboarding(
        payload: GitHubOnboardingRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        from .github_onboarding import GitHubOnboardingEngine, GitHubOnboardingRejected

        engine = GitHubOnboardingEngine(foundry_root=foundry_root())
        try:
            guide = engine.start_guide(
                tenant_id=str(actor.tenant_id),
                principal_id=str(actor.principal_id),
                platform_id=payload.platform_id,
                console_base_url=payload.console_base_url,
                now=datetime.now().astimezone(),
                client_id=payload.github_client_id,
            )
        except GitHubOnboardingRejected as error:
            raise HTTPException(status_code=422, detail=error.code) from None
        return guide.to_document()

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
    @application.get("/platform-dialogue", response_class=HTMLResponse, include_in_schema=False)
    def platform_dialogue_home(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        html_path = Path(__file__).with_name("visual_dialogue_ui.html")
        return HTMLResponse(
            html_path.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
                    "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
                    "frame-ancestors 'none'; form-action 'self'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get(
        "/reference-material-consent", response_class=HTMLResponse, include_in_schema=False
    )
    def reference_material_consent_home(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        html_path = Path(__file__).with_name("reference_material_consent_ui.html")
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

    @application.get("/v1/console/reference-material-notice")
    def reference_material_notice(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return {
            "notice_version": NOTICE_VERSION,
            "notice_text": NOTICE_TEXT,
            "notice_digest": reference_digest(NOTICE_TEXT),
            "required_acknowledgements": sorted(REQUIRED_ACKNOWLEDGEMENTS),
            "automatic_merge_allowed": False,
            "deployment_allowed": False,
        }

    @application.post(
        "/v1/console/reference-material-consents", status_code=status.HTTP_201_CREATED
    )
    def record_reference_material_consent(
        payload: ReferenceConsentSubmission,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ReferenceConsentStore, Depends(reference_consents)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        consent = ReferenceUseConsent(
            request_digest=reference_digest(payload.request.model_dump(mode="json")),
            notice_version=NOTICE_VERSION,
            acknowledged_items=payload.acknowledged_items,
            principal_id=actor.principal_id,
            nonce=payload.nonce,
            confirmed_at=datetime.now(UTC),
        )
        try:
            return store.record(payload.request, consent)
        except ReferenceConsentError as error:
            code = 409 if str(error) == "REFERENCE_CONSENT_ALREADY_RECORDED" else 422
            raise HTTPException(status_code=code, detail=str(error)) from None

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
        return [
            {
                "task_id": item.task_id,
                "job_id": item.job_id,
                "stage": item.stage.value,
                "reason_code": item.reason_code,
                "evidence_fingerprint": item.evidence_fingerprint,
                "expires_at": item.expires_at.isoformat(),
                "status": item.status.value,
            }
            for item in items
        ]

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
            return list(
                store.list_candidate_manifests_for_principal(
                    str(actor.tenant_id), str(actor.principal_id), limit=limit, offset=offset
                )
            )
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
        "/console/api/reviews/{task_id}/decisions",
        status_code=status.HTTP_202_ACCEPTED,
        include_in_schema=False,
    )
    @application.post(
        "/v1/console/reviews/{task_id}/decisions", status_code=status.HTTP_202_ACCEPTED
    )
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
        if (
            payload.task_id != task_id
            or payload.tenant_id != actor.tenant_id
            or payload.principal_id != actor.principal_id
        ):
            raise HTTPException(status_code=403, detail="review binding mismatch")
        try:
            decided = store.decide_review(str(actor.tenant_id), str(task_id), payload.attestation())
        except (DurableStoreError, sqlite3.Error, OSError) as error:
            raise store_error(error) from None
        return {
            "task_id": decided.task_id,
            "decision": payload.decision.value,
            "status": decided.status.value,
        }

    @application.get("/v1/console/self-improvement-reports")
    def plain_reports(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[PlainLanguageApprovalStore, Depends(approvals)],
    ) -> list[dict[str, object]]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.list_reports()

    @application.get("/v1/console/self-improvement-reports/{request_id}")
    def plain_report(
        request_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[PlainLanguageApprovalStore, Depends(approvals)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.get_report(request_id)
        except PlainApprovalError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None

    @application.post("/v1/console/self-improvement-reports/{request_id}/decision")
    def decide_plain_report(
        request_id: str,
        payload: ApprovalDecision,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[PlainLanguageApprovalStore, Depends(approvals)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.decide(
                request_id=request_id, decision=payload, principal_id=str(actor.principal_id)
            )
        except PlainApprovalError as error:
            code = 409 if str(error) == "PLAIN_APPROVAL_ALREADY_DECIDED" else 422
            raise HTTPException(status_code=code, detail=str(error)) from None

    def site_draft_error(error: SiteDraftError) -> HTTPException:
        return HTTPException(
            status_code=409
            if str(error)
            in {"SITE_DRAFT_BUSY", "SITE_DRAFT_CONCURRENT_UPDATE", "SITE_DRAFT_STALE_REVISION"}
            else 422,
            detail=str(error),
        )

    @application.get("/site-drafts", response_class=HTMLResponse, include_in_schema=False)
    def site_drafts_home(actor: Annotated[ConsolePrincipal, Depends(principal)]) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return HTMLResponse(
            Path(__file__)
            .with_name("conversational_site_draft_ui.html")
            .read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.post("/v1/console/site-drafts", status_code=status.HTTP_201_CREATED)
    def create_site_draft(
        payload: SiteDraftRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.create(
            tenant_id=str(actor.tenant_id),
            owner_principal_id=str(actor.principal_id),
            request=payload,
        )

    @application.get("/v1/console/site-drafts")
    def list_site_drafts(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
    ) -> list[dict[str, object]]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.list_for_owner(
            tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
        )

    @application.get("/v1/console/site-drafts/{draft_id}")
    def get_site_draft(
        draft_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.get(
                draft_id, tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
            )
        except SiteDraftError as error:
            raise site_draft_error(error) from None

    @application.get("/v1/console/site-drafts/{draft_id}/revisions/{number}/preview.html")
    def site_draft_preview(
        draft_id: str,
        number: int,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
    ) -> Response:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            page = store.preview(
                draft_id,
                number,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
            )
        except SiteDraftError as error:
            raise site_draft_error(error) from None
        return Response(
            page,
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.post("/v1/console/site-drafts/{draft_id}/revisions")
    def revise_site_draft(
        draft_id: str,
        payload: SiteDraftRevisionRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.revise(
                draft_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                request=payload,
            )
        except SiteDraftError as error:
            raise site_draft_error(error) from None

    @application.post("/v1/console/site-drafts/{draft_id}/rollback/{number}")
    def rollback_site_draft(
        draft_id: str,
        number: int,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.rollback(
                draft_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                revision_number=number,
            )
        except SiteDraftError as error:
            raise site_draft_error(error) from None

    @application.post("/v1/console/site-drafts/{draft_id}/approval-request")
    def request_site_draft_approval(
        draft_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.request_approval(
                draft_id, tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
            )
        except SiteDraftError as error:
            raise site_draft_error(error) from None

    def logo_draft_error(error: LogoDraftError) -> HTTPException:
        return HTTPException(
            status_code=409
            if str(error)
            in {"LOGO_DRAFT_BUSY", "LOGO_DRAFT_CONCURRENT_UPDATE", "LOGO_DRAFT_STALE_REVISION"}
            else 422,
            detail=str(error),
        )

    @application.get("/logo-drafts", response_class=HTMLResponse, include_in_schema=False)
    def logo_drafts_home(actor: Annotated[ConsolePrincipal, Depends(principal)]) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return HTMLResponse(
            Path(__file__).with_name("logo_draft_ui.html").read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.post("/v1/console/logo-drafts", status_code=status.HTTP_201_CREATED)
    def create_logo_draft(
        payload: LogoDraftRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[LogoDraftStore, Depends(logo_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.create(
            tenant_id=str(actor.tenant_id),
            owner_principal_id=str(actor.principal_id),
            request=payload,
        )

    @application.get("/v1/console/logo-drafts")
    def list_logo_drafts(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[LogoDraftStore, Depends(logo_drafts)],
    ) -> list[dict[str, object]]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.list_for_owner(
            tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
        )

    @application.get("/v1/console/logo-drafts/{draft_id}")
    def get_logo_draft(
        draft_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[LogoDraftStore, Depends(logo_drafts)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.get(
                draft_id, tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
            )
        except LogoDraftError as error:
            raise logo_draft_error(error) from None

    @application.post("/v1/console/logo-drafts/{draft_id}/revisions")
    def revise_logo_draft(
        draft_id: str,
        payload: LogoRevisionRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[LogoDraftStore, Depends(logo_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.revise(
                draft_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                request=payload,
            )
        except LogoDraftError as error:
            raise logo_draft_error(error) from None

    @application.post("/v1/console/logo-drafts/{draft_id}/rollback/{number}")
    def rollback_logo_draft(
        draft_id: str,
        number: int,
        payload: LogoRollbackRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[LogoDraftStore, Depends(logo_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.rollback(
                draft_id,
                number,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                based_on_revision_digest=payload.based_on_revision_digest,
            )
        except LogoDraftError as error:
            raise logo_draft_error(error) from None

    @application.get("/v1/console/logo-drafts/{draft_id}/download.svg")
    def download_logo_draft(
        draft_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[LogoDraftStore, Depends(logo_drafts)],
    ) -> Response:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            svg, filename = store.download(
                draft_id, tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
            )
        except LogoDraftError as error:
            raise logo_draft_error(error) from None
        return Response(
            svg,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def business_card_error(error: BusinessCardError) -> HTTPException:
        return HTTPException(
            status_code=409
            if str(error)
            in {
                "BUSINESS_CARD_BUSY",
                "BUSINESS_CARD_CONCURRENT_UPDATE",
                "BUSINESS_CARD_STALE_REVISION",
            }
            else 422,
            detail=str(error),
        )

    @application.get("/business-cards", response_class=HTMLResponse, include_in_schema=False)
    def business_cards_home(actor: Annotated[ConsolePrincipal, Depends(principal)]) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return HTMLResponse(
            Path(__file__).with_name("business_card_ui.html").read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.post("/v1/console/business-cards", status_code=status.HTTP_201_CREATED)
    def create_business_card(
        payload: BusinessCardRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[BusinessCardStore, Depends(business_cards)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.create(
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                request=payload,
            )
        except BusinessCardError as error:
            raise business_card_error(error) from None

    @application.get("/v1/console/business-cards")
    def list_business_cards(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[BusinessCardStore, Depends(business_cards)],
    ) -> list[dict[str, object]]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.list_for_owner(
            tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
        )

    @application.get("/v1/console/business-cards/{card_id}")
    def get_business_card(
        card_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[BusinessCardStore, Depends(business_cards)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.get(
                card_id, tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
            )
        except BusinessCardError as error:
            raise business_card_error(error) from None

    @application.post("/v1/console/business-cards/{card_id}/revisions")
    def revise_business_card(
        card_id: str,
        payload: BusinessCardRevisionRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[BusinessCardStore, Depends(business_cards)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.revise(
                card_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                request=payload,
            )
        except BusinessCardError as error:
            raise business_card_error(error) from None

    @application.post("/v1/console/business-cards/{card_id}/rollback/{number}")
    def rollback_business_card(
        card_id: str,
        number: int,
        payload: BusinessCardRollbackRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[BusinessCardStore, Depends(business_cards)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.rollback(
                card_id,
                number,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                based_on_revision_digest=payload.based_on_revision_digest,
            )
        except BusinessCardError as error:
            raise business_card_error(error) from None

    @application.get("/v1/console/business-cards/{card_id}/download/{side}.svg")
    def download_business_card(
        card_id: str,
        side: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[BusinessCardStore, Depends(business_cards)],
    ) -> Response:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            svg, filename = store.download(
                card_id,
                side,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
            )
        except BusinessCardError as error:
            raise business_card_error(error) from None
        return Response(
            svg,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def visual_error(error: VisualDialogueError) -> HTTPException:
        code = (
            409
            if str(error)
            in {
                "VISUAL_DIALOGUE_BUSY",
                "VISUAL_DIALOGUE_CONCURRENT_UPDATE",
                "VISUAL_REVISION_STALE_BASE",
                "VISUAL_ARTIFACT_CONFLICT",
            }
            else 422
        )
        return HTTPException(status_code=code, detail=str(error))

    @application.post("/v1/console/platform-dialogues", status_code=status.HTTP_201_CREATED)
    def create_platform_dialogue(
        payload: PlatformBrief,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.create(
            tenant_id=str(actor.tenant_id),
            owner_principal_id=str(actor.principal_id),
            brief=payload,
        )

    @application.get("/v1/console/platform-dialogues")
    def list_platform_dialogues(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
    ) -> list[dict[str, object]]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return store.list_for_owner(
            tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id)
        )

    @application.get("/v1/console/platform-dialogues/{dialogue_id}")
    def get_platform_dialogue(
        dialogue_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
    ) -> dict[str, object]:
        if actor.role not in {"owner", "operator"}:
            raise HTTPException(status_code=403, detail="platform dialogue role required")
        try:
            return store.get(dialogue_id, tenant_id=str(actor.tenant_id))
        except VisualDialogueError as error:
            raise visual_error(error) from None

    @application.post("/v1/console/platform-dialogues/{dialogue_id}/revisions")
    def submit_platform_revision(
        dialogue_id: str,
        payload: RevisionSubmission,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "operator":
            raise HTTPException(status_code=403, detail="ARKAON operator role required")
        try:
            return store.submit_revision(
                dialogue_id, tenant_id=str(actor.tenant_id), submission=payload
            )
        except VisualDialogueError as error:
            raise visual_error(error) from None

    @application.get("/v1/console/platform-dialogues/{dialogue_id}/revisions/{number}/preview.svg")
    def platform_revision_image(
        dialogue_id: str,
        number: int,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
    ) -> Response:
        if actor.role not in {"owner", "operator"}:
            raise HTTPException(status_code=403, detail="platform dialogue role required")
        try:
            data = store.image(dialogue_id, number, tenant_id=str(actor.tenant_id))
        except VisualDialogueError as error:
            raise visual_error(error) from None
        return Response(
            content=data,
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @application.post("/v1/console/platform-dialogues/{dialogue_id}/feedback")
    def request_platform_revision(
        dialogue_id: str,
        payload: RevisionFeedback,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.add_feedback(
                dialogue_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                feedback=payload,
            )
        except VisualDialogueError as error:
            raise visual_error(error) from None

    @application.post("/v1/console/platform-dialogues/{dialogue_id}/understanding")
    def confirm_platform_understanding(
        dialogue_id: str,
        payload: UnderstandingConfirmation,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.confirm(
                dialogue_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                confirmation=payload,
            )
        except VisualDialogueError as error:
            raise visual_error(error) from None

    @application.post("/v1/console/platform-dialogues/{dialogue_id}/seal")
    def seal_platform_specification(
        dialogue_id: str,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.seal(
                dialogue_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
            )
        except VisualDialogueError as error:
            raise visual_error(error) from None


def console_security_from_config(
    *, environment: str | None = None, secret: str | None = None
) -> ConsoleSecurity:
    return ConsoleSecurity(
        environment=environment or os.getenv("APF_ENV", "development"),
        secret=secret or os.getenv("APF_CONSOLE_SESSION_SECRET"),
        allow_dev_sessions=os.getenv("APF_ENABLE_DEV_SESSION", "").lower() == "true",
    )
