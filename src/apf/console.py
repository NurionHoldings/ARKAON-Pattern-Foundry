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
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

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
from .design_reference_urls import (
    DesignReferenceBatch,
    DesignReferenceError,
    DesignReferenceStore,
    SubjectType,
)
from .design_style_proposal import (
    StyleDecision,
    StyleProposalError,
    StyleProposalRequest,
    StyleProposalStore,
    inject_preview_style,
    render_style_css,
)
from .durable_review import (
    DurableStoreError,
    ReviewAttestation,
    ReviewDecision,
    ReviewStage,
)
from .github_owner_auth import GitHubOwnerAuth, OwnerAuthError
from .logo_draft import (
    LogoDraftError,
    LogoDraftRequest,
    LogoDraftStore,
    LogoRevisionRequest,
    LogoRollbackRequest,
)
from .logo_motion import Motion
from .logo_reference import ImageReferenceError, ImageReferenceRequest, analyze_reference
from .plain_language_approval import (
    ApprovalDecision,
    PlainApprovalError,
    PlainLanguageApprovalStore,
)
from .platform_page_preview import PageKind
from .popular_format import Decision as FormatDecision
from .popular_format import ProposalRequest, ProposalStore
from .popular_format import build as build_format
from .public_page_observer import ObservationError, PublicPageObserver
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
OAUTH_STATE_COOKIE = "apf_console_oauth_state"
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


class DesignCaptureRequest(BaseModel):
    based_on_set_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reference_id: UUID
    consent_request_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


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
    owner_auth: GitHubOwnerAuth | None = None,
    review_store: ConsoleReviewStore | None = None,
    approval_store: PlainLanguageApprovalStore | None = None,
    visual_dialogue_store: VisualPlatformDialogueStore | None = None,
    conversational_site_draft_store: ConversationalSiteDraftStore | None = None,
    logo_draft_store: LogoDraftStore | None = None,
    business_card_store: BusinessCardStore | None = None,
    reference_consent_store: ReferenceConsentStore | None = None,
    design_reference_store: DesignReferenceStore | None = None,
    style_proposal_store: StyleProposalStore | None = None,
    public_page_observer: PublicPageObserver | None = None,
    format_proposal_store: ProposalStore | None = None,
) -> None:
    application.state.console_security = security
    application.state.console_review_store = review_store
    application.state.plain_approval_store = approval_store
    application.state.visual_dialogue_store = visual_dialogue_store
    application.state.conversational_site_draft_store = conversational_site_draft_store
    application.state.logo_draft_store = logo_draft_store
    application.state.business_card_store = business_card_store
    application.state.reference_consent_store = reference_consent_store
    application.state.design_reference_store = design_reference_store
    application.state.style_proposal_store = style_proposal_store
    application.state.public_page_observer = public_page_observer
    application.state.format_proposal_store = format_proposal_store

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

    def design_references(request: Request) -> DesignReferenceStore:
        store = request.app.state.design_reference_store
        if store is None:
            raise HTTPException(status_code=503, detail="design reference store unavailable")
        return store

    def style_proposals(request: Request) -> StyleProposalStore:
        store = request.app.state.style_proposal_store
        if store is None:
            raise HTTPException(status_code=503, detail="style proposal store unavailable")
        return store

    def public_observer(request: Request) -> PublicPageObserver:
        observer = request.app.state.public_page_observer
        if observer is None:
            raise HTTPException(status_code=503, detail="public page observer unavailable")
        return observer

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

    @application.get("/console/auth/github", include_in_schema=False)
    def start_owner_sign_in() -> RedirectResponse:
        if owner_auth is None:
            raise HTTPException(status_code=503, detail="owner sign-in unavailable")
        destination, state_cookie = owner_auth.start()
        response = RedirectResponse(destination, status_code=302)
        response.set_cookie(
            OAUTH_STATE_COOKIE, state_cookie, max_age=300, httponly=True,
            secure=True, samesite="lax", path="/console/auth",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/console/auth/callback", include_in_schema=False)
    def finish_owner_sign_in(
        code: str, state: str,
        state_cookie: Annotated[str | None, Cookie(alias=OAUTH_STATE_COOKIE)] = None,
    ) -> RedirectResponse:
        if owner_auth is None:
            raise HTTPException(status_code=503, detail="owner sign-in unavailable")
        try:
            identity = owner_auth.verify_callback(code=code, state=state, cookie=state_cookie)
        except OwnerAuthError as error:
            raise HTTPException(status_code=403, detail=str(error)) from None
        token = security.issue(ConsolePrincipal(
            tenant_id=identity.tenant_id, principal_id=identity.principal_id, role="owner",
        ))
        response = RedirectResponse("/console", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, token, max_age=3600, httponly=True,
            secure=True, samesite="strict", path="/",
        )
        response.set_cookie(
            CSRF_COOKIE, secrets.token_urlsafe(32), max_age=3600,
            httponly=False, secure=True, samesite="strict", path="/",
        )
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/console/auth", secure=True, httponly=True, samesite="lax")
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/v1/console/railway-readiness")
    def railway_readiness(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        path = Path(__file__).resolve().parents[2] / "knowledge/readiness/v0.1-readiness.json"
        try:
            readiness = json.loads(path.read_text(encoding="utf-8"))
            return {
                "overall_status": readiness["overall_status"],
                "deployment_allowed": readiness["locks"]["deployment"] is True,
            }
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(status_code=503, detail="readiness evidence unavailable") from None

    @application.get("/console/railway-setup", response_class=HTMLResponse, include_in_schema=False)
    def railway_setup(actor: Annotated[ConsolePrincipal, Depends(principal)]) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return HTMLResponse(
            Path(__file__).with_name("railway_setup_ui.html").read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

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
                    "script-src 'unsafe-inline'; connect-src 'self'; frame-src 'self'; base-uri 'none'; "
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
    ) -> dict[str, object]:
        targets = repository.list_targets(actor.tenant_id)
        readiness_path = Path(__file__).parents[2] / "knowledge/readiness/v0.1-readiness.json"
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        return {
            "principal": {"role": actor.role, "tenant_id": str(actor.tenant_id)},
            "counts": {"targets": len(targets), "open_reviews": 0, "asset_candidates": 0},
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

    def format_asset(actor: ConsolePrincipal, kind: str, record_id: str) -> dict:
        stores = {
            "site_draft": application.state.conversational_site_draft_store,
            "logo_draft": application.state.logo_draft_store,
            "business_card": application.state.business_card_store,
            "platform_dialogue": application.state.visual_dialogue_store,
        }
        store = stores.get(kind)
        if store is None:
            raise HTTPException(status_code=404, detail="asset not found")
        try:
            if kind == "platform_dialogue":
                asset = store.get_for_owner(record_id, tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id))
            else:
                asset = store.get(record_id, tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id))
        except (SiteDraftError, LogoDraftError, BusinessCardError, VisualDialogueError, ValueError, KeyError):
            raise HTTPException(status_code=404, detail="asset not found") from None
        if not asset.get("intent_dna") or not asset.get("revisions"):
            raise HTTPException(status_code=422, detail="asset has no current intent/DNA revision")
        return asset

    def format_store(request: Request) -> ProposalStore:
        store = request.app.state.format_proposal_store
        if store is None:
            raise HTTPException(status_code=503, detail="format proposal store unavailable")
        return store

    @application.get("/format-proposals", response_class=HTMLResponse, include_in_schema=False)
    def format_proposals_page(actor: Annotated[ConsolePrincipal, Depends(principal)]) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return HTMLResponse(Path(__file__).with_name("popular_format_ui.html").read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})

    @application.post("/v1/console/format-proposals", status_code=201)
    def create_format_proposal(payload: ProposalRequest, request: Request,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)]) -> dict:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        asset = format_asset(actor, payload.artifact_type, payload.record_id)
        latest = asset["revisions"][-1]["revision_digest"]
        if payload.source_revision_digest != latest:
            raise HTTPException(status_code=409, detail="SOURCE_REVISION_CHANGED")
        try:
            proposal = build_format(payload, asset["intent_dna"], str(actor.principal_id), str(actor.tenant_id))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return format_store(request).create(proposal)

    @application.get("/v1/console/format-proposals/{proposal_id}")
    def get_format_proposal(proposal_id: UUID, request: Request,
        actor: Annotated[ConsolePrincipal, Depends(principal)]) -> dict:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return format_store(request).get(str(proposal_id), str(actor.tenant_id), str(actor.principal_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="proposal not found") from None

    @application.post("/v1/console/format-proposals/{proposal_id}/decision")
    def decide_format_proposal(proposal_id: UUID, payload: FormatDecision, request: Request,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)]) -> dict:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        store = format_store(request)
        try:
            doc = store.get(str(proposal_id), str(actor.tenant_id), str(actor.principal_id))
            asset = format_asset(actor, doc["artifact_type"], doc["record_id"])
            return store.decide(str(proposal_id), str(actor.tenant_id), str(actor.principal_id), payload,
                                asset["intent_dna"], asset["revisions"][-1]["revision_digest"])
        except KeyError:
            raise HTTPException(status_code=404, detail="proposal not found") from None
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

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
        references: Annotated[DesignReferenceStore, Depends(design_references)],
        proposals: Annotated[StyleProposalStore, Depends(style_proposals)],
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
        page = approved_style(page, "site_draft", draft_id, actor, references, proposals)
        return Response(
            page,
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.post("/v1/console/site-drafts/{draft_id}/revisions/preview")
    def preview_site_revision(
        draft_id: str,
        payload: SiteDraftRevisionRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, str]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return {
                "html": store.preview_revision(
                    draft_id,
                    tenant_id=str(actor.tenant_id),
                    owner_principal_id=str(actor.principal_id),
                    request=payload,
                )
            }
        except SiteDraftError as error:
            raise site_draft_error(error) from None

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

    @application.post("/v1/console/logo-reference/analyze")
    def analyze_logo_reference(
        payload: ImageReferenceRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return analyze_reference(payload)
        except ImageReferenceError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

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

    @application.get("/v1/console/logo-drafts/{draft_id}/animated.svg")
    def download_animated_logo(
        draft_id: str,
        motion: Motion,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[LogoDraftStore, Depends(logo_drafts)],
    ) -> Response:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            svg, filename = store.animated_download(
                draft_id,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                motion=motion,
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

    @application.post("/v1/console/business-cards/preview")
    def preview_business_card(
        payload: BusinessCardRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[BusinessCardStore, Depends(business_cards)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, str]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            return store.preview(
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                request=payload,
            )
        except BusinessCardError as error:
            raise business_card_error(error) from None

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

    def design_reference_subject(
        subject_type: SubjectType, subject_id: str, actor: ConsolePrincipal,
        site_store: ConversationalSiteDraftStore,
        dialogue_store: VisualPlatformDialogueStore,
    ) -> None:
        try:
            if subject_type == "site_draft":
                site_store.get(
                    subject_id, tenant_id=str(actor.tenant_id),
                    owner_principal_id=str(actor.principal_id),
                )
            else:
                dialogue_store.get_for_owner(
                    subject_id, tenant_id=str(actor.tenant_id),
                    owner_principal_id=str(actor.principal_id),
                )
        except SiteDraftError as error:
            raise site_draft_error(error) from None
        except VisualDialogueError as error:
            raise visual_error(error) from None

    def design_reference_error(error: DesignReferenceError) -> HTTPException:
        code = str(error)
        return HTTPException(
            status_code=404 if code == "DESIGN_REFERENCES_NOT_FOUND"
            else 409 if code in {"DESIGN_REFERENCES_STALE", "DESIGN_REFERENCES_BUSY"}
            else 422,
            detail=code,
        )

    @application.get(
        "/design-references", response_class=HTMLResponse, include_in_schema=False
    )
    def design_reference_home(
        actor: Annotated[ConsolePrincipal, Depends(principal)],
    ) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        return HTMLResponse(
            Path(__file__).with_name("design_reference_ui.html").read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get("/v1/console/design-references/{subject_type}/{subject_id}")
    def get_design_references(
        subject_type: SubjectType,
        subject_id: UUID,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[DesignReferenceStore, Depends(design_references)],
        site_store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        dialogue_store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        design_reference_subject(
            subject_type, str(subject_id), actor, site_store, dialogue_store
        )
        try:
            return store.get(
                subject_type, str(subject_id), tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
            )
        except DesignReferenceError as error:
            if str(error) == "DESIGN_REFERENCES_NOT_FOUND":
                return {
                    "subject_type": subject_type, "subject_id": str(subject_id),
                    "references": [], "set_digest": None, "status": "WAITING_FOR_CAPTURE",
                    "capture_performed": False, "style_applied": False,
                }
            raise design_reference_error(error) from None

    @application.post("/v1/console/design-references/{subject_type}/{subject_id}")
    def append_design_references(
        subject_type: SubjectType,
        subject_id: UUID,
        payload: DesignReferenceBatch,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[DesignReferenceStore, Depends(design_references)],
        site_store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        dialogue_store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        design_reference_subject(
            subject_type, str(subject_id), actor, site_store, dialogue_store
        )
        try:
            return store.append(
                subject_type, str(subject_id), tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id), batch=payload,
            )
        except DesignReferenceError as error:
            raise design_reference_error(error) from None

    @application.post("/v1/console/design-references/{subject_type}/{subject_id}/capture")
    def capture_design_reference(
        subject_type: SubjectType, subject_id: UUID, payload: DesignCaptureRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        references: Annotated[DesignReferenceStore, Depends(design_references)],
        consents: Annotated[ReferenceConsentStore, Depends(reference_consents)],
        observer: Annotated[PublicPageObserver, Depends(public_observer)],
        site_store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        dialogue_store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        design_reference_subject(subject_type, str(subject_id), actor, site_store, dialogue_store)
        selected = reference_set(subject_type, str(subject_id), actor, references)
        if payload.based_on_set_digest != selected["set_digest"]:
            raise HTTPException(status_code=409, detail="DESIGN_CAPTURE_REFERENCES_STALE")
        reference = next(
            (item for item in selected["references"]
             if item["reference_id"] == str(payload.reference_id)), None
        )
        if reference is None:
            raise HTTPException(status_code=404, detail="DESIGN_CAPTURE_REFERENCE_NOT_FOUND")
        try:
            consents.verify_analysis_receipt(
                payload.consent_request_id, principal_id=str(actor.principal_id),
                source_id=str(payload.reference_id), source_locator=str(reference["url"]),
                scope_digest=payload.based_on_set_digest,
            )
        except ReferenceConsentError as error:
            raise HTTPException(status_code=403, detail=str(error)) from None
        try:
            return observer.observe(str(reference["url"]), payload.reference_id)
        except ObservationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    def style_error(error: StyleProposalError) -> HTTPException:
        code = str(error)
        return HTTPException(
            status_code=404 if code == "STYLE_NOT_FOUND"
            else 409 if code in {"STYLE_BUSY", "STYLE_REFERENCES_STALE", "STYLE_DECISION_STALE"}
            else 422, detail=code,
        )

    def reference_set(
        subject_type: SubjectType, subject_id: str, actor: ConsolePrincipal,
        references: DesignReferenceStore,
    ) -> dict[str, object]:
        try:
            return references.get(
                subject_type, subject_id, tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
            )
        except DesignReferenceError as error:
            raise design_reference_error(error) from None

    @application.post("/v1/console/design-references/{subject_type}/{subject_id}/style")
    def propose_reference_style(
        subject_type: SubjectType, subject_id: UUID, payload: StyleProposalRequest,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        references: Annotated[DesignReferenceStore, Depends(design_references)],
        proposals: Annotated[StyleProposalStore, Depends(style_proposals)],
        site_store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        dialogue_store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        design_reference_subject(subject_type, str(subject_id), actor, site_store, dialogue_store)
        selected = reference_set(subject_type, str(subject_id), actor, references)
        try:
            return proposals.propose(
                subject_type, str(subject_id), tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                references=selected, request=payload,
            )
        except StyleProposalError as error:
            raise style_error(error) from None

    @application.get("/v1/console/design-references/{subject_type}/{subject_id}/style")
    def get_reference_style(
        subject_type: SubjectType, subject_id: UUID,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        references: Annotated[DesignReferenceStore, Depends(design_references)],
        proposals: Annotated[StyleProposalStore, Depends(style_proposals)],
        site_store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        dialogue_store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
    ) -> dict[str, object]:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        design_reference_subject(subject_type, str(subject_id), actor, site_store, dialogue_store)
        selected = reference_set(subject_type, str(subject_id), actor, references)
        try:
            return proposals.get(
                subject_type, str(subject_id), tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                reference_set_digest=str(selected["set_digest"]),
            )
        except StyleProposalError as error:
            raise style_error(error) from None

    @application.post("/v1/console/design-references/{subject_type}/{subject_id}/style/decision")
    def decide_reference_style(
        subject_type: SubjectType, subject_id: UUID, payload: StyleDecision,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        references: Annotated[DesignReferenceStore, Depends(design_references)],
        proposals: Annotated[StyleProposalStore, Depends(style_proposals)],
        site_store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        dialogue_store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        csrf_verified: Annotated[None, Depends(csrf_guard)],
    ) -> dict[str, object]:
        del csrf_verified
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        design_reference_subject(subject_type, str(subject_id), actor, site_store, dialogue_store)
        selected = reference_set(subject_type, str(subject_id), actor, references)
        try:
            return proposals.decide(
                subject_type, str(subject_id), tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                reference_set_digest=str(selected["set_digest"]), decision=payload,
            )
        except StyleProposalError as error:
            raise style_error(error) from None

    @application.get("/v1/console/design-references/{subject_type}/{subject_id}/style/preview/{kind}")
    def preview_reference_style(
        subject_type: SubjectType, subject_id: UUID, kind: PageKind,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        references: Annotated[DesignReferenceStore, Depends(design_references)],
        proposals: Annotated[StyleProposalStore, Depends(style_proposals)],
        site_store: Annotated[ConversationalSiteDraftStore, Depends(site_drafts)],
        dialogue_store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
    ) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        design_reference_subject(subject_type, str(subject_id), actor, site_store, dialogue_store)
        selected = reference_set(subject_type, str(subject_id), actor, references)
        try:
            proposal = proposals.get(
                subject_type, str(subject_id), tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                reference_set_digest=str(selected["set_digest"]),
            )
            if proposal["status"] == "REJECTED":
                raise StyleProposalError("STYLE_REJECTED")
            if subject_type == "site_draft":
                if kind != "home":
                    raise StyleProposalError("STYLE_PREVIEW_KIND_INVALID")
                draft = site_store.get(
                    str(subject_id), tenant_id=str(actor.tenant_id),
                    owner_principal_id=str(actor.principal_id),
                )
                page = site_store.preview(
                    str(subject_id), int(draft["revision_count"]),
                    tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id),
                )
            else:
                dialogue = dialogue_store.get_for_owner(
                    str(subject_id), tenant_id=str(actor.tenant_id),
                    owner_principal_id=str(actor.principal_id),
                )
                page = dialogue_store.page_preview(
                    str(subject_id), int(dialogue["revision_count"]), kind,
                    tenant_id=str(actor.tenant_id), owner_principal_id=str(actor.principal_id),
                )
            page = inject_preview_style(page, render_style_css(proposal["tokens"]))
        except StyleProposalError as error:
            raise style_error(error) from None
        return HTMLResponse(
            page, headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def approved_style(
        page: str, subject_type: SubjectType, subject_id: str, actor: ConsolePrincipal,
        references: DesignReferenceStore, proposals: StyleProposalStore,
    ) -> str:
        try:
            selected = references.get(
                subject_type, subject_id, tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
            )
            proposal = proposals.get(
                subject_type, subject_id, tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
                reference_set_digest=str(selected["set_digest"]),
            )
        except DesignReferenceError as error:
            if str(error) == "DESIGN_REFERENCES_NOT_FOUND":
                return page
            raise design_reference_error(error) from None
        except StyleProposalError as error:
            if str(error) in {"STYLE_NOT_FOUND", "STYLE_REFERENCES_STALE"}:
                return page
            raise style_error(error) from None
        if proposal["status"] == "APPLIED":
            return inject_preview_style(page, render_style_css(proposal["tokens"]))
        return page

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

    @application.get(
        "/v1/console/platform-dialogues/{dialogue_id}/revisions/{number}/page/{kind}.html",
        response_class=HTMLResponse,
    )
    def platform_page_preview(
        dialogue_id: str,
        number: int,
        kind: PageKind,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        store: Annotated[VisualPlatformDialogueStore, Depends(visual_dialogues)],
        references: Annotated[DesignReferenceStore, Depends(design_references)],
        proposals: Annotated[StyleProposalStore, Depends(style_proposals)],
    ) -> HTMLResponse:
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="owner role required")
        try:
            page = store.page_preview(
                dialogue_id, number, kind,
                tenant_id=str(actor.tenant_id),
                owner_principal_id=str(actor.principal_id),
            )
        except VisualDialogueError as error:
            raise visual_error(error) from None
        page = approved_style(page, "platform_dialogue", dialogue_id, actor, references, proposals)
        return HTMLResponse(
            page,
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'",
                "X-Content-Type-Options": "nosniff",
            },
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
