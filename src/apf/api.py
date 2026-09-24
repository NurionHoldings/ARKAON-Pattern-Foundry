from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from .business_card import BusinessCardStore
from .console import (
    ConsoleReviewStore,
    ConsoleSecurity,
    console_security_from_config,
    install_console,
)
from .conversational_site_draft import ConversationalSiteDraftStore
from .design_reference_urls import DesignReferenceStore
from .design_style_proposal import StyleProposalStore
from .domain import AnalysisTarget, AnalysisTargetCreate, TargetState
from .github_owner_auth import GitHubOwnerAuth
from .logo_draft import LogoDraftStore
from .plain_language_approval import PlainLanguageApprovalStore
from .public_page_observer import PublicPageObserver
from .reference_material_consent import ReferenceConsentStore
from .repository import (
    DuplicateTarget,
    MemoryRepository,
    NotFound,
    PostgresRepository,
    RevisionConflict,
    TargetRepository,
)
from .state_machine import TARGET_TRANSITIONS, InvalidTransition, transition
from .visual_platform_dialogue import VisualPlatformDialogueStore

TenantHeader = Annotated[UUID, Header(alias="X-Tenant-ID")]
RevisionHeader = Annotated[int, Header(alias="If-Match")]


def tenant(x_tenant_id: TenantHeader) -> UUID:
    return x_tenant_id


def request_repository(request: Request) -> TargetRepository:
    return request.app.state.repository


def repository_from_config(
    *, environment: str | None = None, database_url: str | None = None
) -> TargetRepository:
    environment = (environment or os.getenv("APF_ENV", "development")).lower()
    database_url = database_url or os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("DATABASE_URL must use PostgreSQL")
        return PostgresRepository(database_url)
    if environment in {"production", "prod"}:
        raise RuntimeError("DATABASE_URL is required in production; memory fallback is disabled")
    return MemoryRepository()


def runtime_root() -> Path:
    """Keep the new logo and business-card artifacts outside the checkout by default."""
    configured = os.getenv("APF_RUNTIME_ROOT")
    if not configured and os.getenv("APF_ENV", "development").lower() in {"production", "prod"}:
        raise RuntimeError("APF_RUNTIME_ROOT is required in production")
    return Path(configured or Path(tempfile.gettempdir()) / "apf-runtime")


def create_app(
    *,
    repository: TargetRepository | None = None,
    console_security: ConsoleSecurity | None = None,
    owner_auth: GitHubOwnerAuth | None = None,
    console_review_store: ConsoleReviewStore | None = None,
    plain_approval_store: PlainLanguageApprovalStore | None = None,
    visual_dialogue_store: VisualPlatformDialogueStore | None = None,
    conversational_site_draft_store: ConversationalSiteDraftStore | None = None,
    logo_draft_store: LogoDraftStore | None = None,
    business_card_store: BusinessCardStore | None = None,
    reference_consent_store: ReferenceConsentStore | None = None,
    design_reference_store: DesignReferenceStore | None = None,
    style_proposal_store: StyleProposalStore | None = None,
    public_page_observer: PublicPageObserver | None = None,
) -> FastAPI:
    application = FastAPI(title="ARKAON Pattern Foundry", version="0.1.0")
    application.state.repository = repository or repository_from_config()
    logo_store = logo_draft_store or LogoDraftStore(runtime_root())
    install_console(
        application,
        security=console_security or console_security_from_config(),
        owner_auth=owner_auth or GitHubOwnerAuth.from_environment(),
        review_store=console_review_store,
        approval_store=plain_approval_store
        or PlainLanguageApprovalStore(
            Path(os.getenv("APF_FOUNDRY_ROOT", Path(__file__).parents[2]))
        ),
        visual_dialogue_store=visual_dialogue_store
        or VisualPlatformDialogueStore(
            Path(os.getenv("APF_FOUNDRY_ROOT", Path(__file__).parents[2]))
        ),
        conversational_site_draft_store=conversational_site_draft_store
        or ConversationalSiteDraftStore(
            Path(os.getenv("APF_FOUNDRY_ROOT", Path(__file__).parents[2]))
        ),
        logo_draft_store=logo_store,
        business_card_store=business_card_store or BusinessCardStore(runtime_root(), logo_store),
        design_reference_store=design_reference_store or DesignReferenceStore(runtime_root()),
        style_proposal_store=style_proposal_store or StyleProposalStore(runtime_root()),
        public_page_observer=public_page_observer or PublicPageObserver(),
        reference_consent_store=reference_consent_store
        or ReferenceConsentStore(Path(os.getenv("APF_FOUNDRY_ROOT", Path(__file__).parents[2]))),
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post(
        "/v1/targets", response_model=AnalysisTarget, status_code=status.HTTP_201_CREATED
    )
    def create_target(
        payload: AnalysisTargetCreate,
        tenant_id: Annotated[UUID, Depends(tenant)],
        repository: Annotated[TargetRepository, Depends(request_repository)],
    ) -> AnalysisTarget:
        if payload.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="tenant mismatch")
        try:
            return repository.create_target(payload)
        except NotFound:
            raise HTTPException(status_code=404, detail="tenant not provisioned") from None
        except DuplicateTarget:
            raise HTTPException(status_code=409, detail="target identity conflict") from None

    @application.get("/v1/targets/{target_id}", response_model=AnalysisTarget)
    def get_target(
        target_id: UUID,
        tenant_id: Annotated[UUID, Depends(tenant)],
        repository: Annotated[TargetRepository, Depends(request_repository)],
    ) -> AnalysisTarget:
        try:
            return repository.get_target(target_id, tenant_id)
        except NotFound:
            raise HTTPException(status_code=404, detail="target not found") from None

    @application.post("/v1/targets/{target_id}/transitions", response_model=AnalysisTarget)
    def transition_target(
        target_id: UUID,
        desired: TargetState,
        expected_revision: RevisionHeader,
        tenant_id: Annotated[UUID, Depends(tenant)],
        repository: Annotated[TargetRepository, Depends(request_repository)],
    ) -> AnalysisTarget:
        try:
            current = repository.get_target(target_id, tenant_id)
            transition(current.state, desired, TARGET_TRANSITIONS)
            return repository.set_target_state(target_id, tenant_id, expected_revision, desired)
        except NotFound:
            raise HTTPException(status_code=404, detail="target not found") from None
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="revision conflict") from None
        except InvalidTransition as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return application


app = create_app()
