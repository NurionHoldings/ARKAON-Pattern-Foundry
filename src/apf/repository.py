from __future__ import annotations

from threading import RLock
from uuid import UUID

from .domain import AnalysisTarget, AnalysisTargetCreate, TargetState


class NotFound(KeyError):
    pass


class RevisionConflict(RuntimeError):
    pass


class MemoryRepository:
    """Thread-safe reference repository; production adapter is PostgreSQL."""

    def __init__(self) -> None:
        self._targets: dict[UUID, AnalysisTarget] = {}
        self._lock = RLock()

    def create_target(self, value: AnalysisTargetCreate) -> AnalysisTarget:
        target = AnalysisTarget(**value.model_dump())
        with self._lock:
            self._targets[target.id] = target
        return target.model_copy(deep=True)

    def get_target(self, target_id: UUID, tenant_id: UUID) -> AnalysisTarget:
        with self._lock:
            target = self._targets.get(target_id)
            if target is None or target.tenant_id != tenant_id:
                raise NotFound(target_id)
            return target.model_copy(deep=True)

    def set_target_state(self, target_id: UUID, tenant_id: UUID, expected_revision: int, state: TargetState) -> AnalysisTarget:
        with self._lock:
            target = self._targets.get(target_id)
            if target is None or target.tenant_id != tenant_id:
                raise NotFound(target_id)
            if target.revision != expected_revision:
                raise RevisionConflict(target_id)
            updated = target.model_copy(update={"state": state, "revision": target.revision + 1})
            self._targets[target_id] = updated
            return updated.model_copy(deep=True)

