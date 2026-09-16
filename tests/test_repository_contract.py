from uuid import UUID, uuid4

import pytest

from apf.domain import (
    AnalysisTargetCreate,
    Classification,
    ScopePermissions,
    TargetState,
    TargetType,
)
from apf.repository import DuplicateTarget, MemoryRepository, NotFound, RevisionConflict


def make_value(tenant_id: UUID, *, name: str = "MJN") -> AnalysisTargetCreate:
    return AnalysisTargetCreate(
        tenant_id=tenant_id,
        name=name,
        target_type=TargetType.OWNED_SYSTEM,
        classification=Classification.INTERNAL,
        permissions=ScopePermissions(read=True, parse=True, derive=True),
        source_evidence_ids=[uuid4()],
    )


def assert_repository_contract(repository, tenant_id: UUID) -> None:
    value = make_value(tenant_id)
    created = repository.create_target(value)
    assert created.created_at.utcoffset().total_seconds() == 0
    assert repository.create_target(value).id == created.id
    assert repository.get_target(created.id, tenant_id) == created
    with pytest.raises(NotFound):
        repository.get_target(created.id, uuid4())

    changed = value.model_copy(update={"source_evidence_ids": [uuid4()]})
    with pytest.raises(DuplicateTarget):
        repository.create_target(changed)

    moved = repository.set_target_state(created.id, tenant_id, 0, TargetState.AUTHORIZATION_PENDING)
    assert moved.revision == 1
    with pytest.raises(RevisionConflict):
        repository.set_target_state(created.id, tenant_id, 0, TargetState.AUTHORIZATION_PENDING)


def test_memory_repository_contract():
    assert_repository_contract(MemoryRepository(), uuid4())
