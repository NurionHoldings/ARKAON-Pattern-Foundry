from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from .console import (
    ConsoleReviewStore,
    ConsoleSecurity,
    console_security_from_config,
    install_console,
)
from .domain import AnalysisTarget, AnalysisTargetCreate, TargetState
from .repository import (
    DuplicateTarget,
    MemoryRepository,
    NotFound,
    PostgresRepository,
    RevisionConflict,
    TargetRepository,
)
from .state_machine import TARGET_TRANSITIONS, InvalidTransition, transition

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
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("DATABASE_URL must use PostgreSQL")
        return PostgresRepository(database_url)
    if environment in {"production", "prod"}:
        raise RuntimeError("DATABASE_URL is required in production; memory fallback is disabled")
    return MemoryRepository()


def create_app(
    *, repository: TargetRepository | None = None, console_security: ConsoleSecurity | None = None,
    console_review_store: ConsoleReviewStore | None = None,
) -> FastAPI:
    application = FastAPI(title="ARKAON Pattern Foundry", version="0.1.0")
    application.state.repository = repository or repository_from_config()
    install_console(
        application, security=console_security or console_security_from_config(),
        review_store=console_review_store,
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/v1/targets", response_model=AnalysisTarget, status_code=status.HTTP_201_CREATED)
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
