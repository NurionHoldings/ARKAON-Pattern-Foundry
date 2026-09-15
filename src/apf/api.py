from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .domain import AnalysisTarget, AnalysisTargetCreate, TargetState
from .repository import MemoryRepository, NotFound, RevisionConflict
from .state_machine import TARGET_TRANSITIONS, InvalidTransition, transition

app = FastAPI(title="ARKAON Pattern Foundry", version="0.1.0")
repo = MemoryRepository()


TenantHeader = Annotated[UUID, Header(alias="X-Tenant-ID")]
RevisionHeader = Annotated[int, Header(alias="If-Match")]


def tenant(x_tenant_id: TenantHeader) -> UUID:
    return x_tenant_id


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/targets", response_model=AnalysisTarget, status_code=status.HTTP_201_CREATED)
def create_target(payload: AnalysisTargetCreate, tenant_id: Annotated[UUID, Depends(tenant)]) -> AnalysisTarget:
    if payload.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="tenant mismatch")
    return repo.create_target(payload)


@app.get("/v1/targets/{target_id}", response_model=AnalysisTarget)
def get_target(target_id: UUID, tenant_id: Annotated[UUID, Depends(tenant)]) -> AnalysisTarget:
    try:
        return repo.get_target(target_id, tenant_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="target not found") from None


@app.post("/v1/targets/{target_id}/transitions", response_model=AnalysisTarget)
def transition_target(
    target_id: UUID,
    desired: TargetState,
    expected_revision: RevisionHeader,
    tenant_id: Annotated[UUID, Depends(tenant)],
) -> AnalysisTarget:
    try:
        current = repo.get_target(target_id, tenant_id)
        transition(current.state, desired, TARGET_TRANSITIONS)
        return repo.set_target_state(target_id, tenant_id, expected_revision, desired)
    except NotFound:
        raise HTTPException(status_code=404, detail="target not found") from None
    except RevisionConflict:
        raise HTTPException(status_code=409, detail="revision conflict") from None
    except InvalidTransition as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
