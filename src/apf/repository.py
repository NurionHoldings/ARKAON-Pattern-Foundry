from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC
from threading import RLock
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from .domain import AnalysisTarget, AnalysisTargetCreate, TargetState


class NotFound(KeyError):
    pass


class RevisionConflict(RuntimeError):
    pass


class DuplicateTarget(RuntimeError):
    """The tenant/name idempotency identity was reused with different content."""


class TargetRepository(Protocol):
    def create_target(self, value: AnalysisTargetCreate) -> AnalysisTarget: ...

    def get_target(self, target_id: UUID, tenant_id: UUID) -> AnalysisTarget: ...

    def list_targets(self, tenant_id: UUID, *, limit: int = 100) -> tuple[AnalysisTarget, ...]: ...

    def set_target_state(
        self, target_id: UUID, tenant_id: UUID, expected_revision: int, state: TargetState
    ) -> AnalysisTarget: ...


def _canonical_create(value: AnalysisTargetCreate) -> str:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class MemoryRepository:
    """Thread-safe reference adapter implementing the production repository contract."""

    def __init__(self) -> None:
        self._targets: dict[UUID, AnalysisTarget] = {}
        self._identity: dict[tuple[UUID, str], UUID] = {}
        self._lock = RLock()

    def create_target(self, value: AnalysisTargetCreate) -> AnalysisTarget:
        with self._lock:
            identity = (value.tenant_id, value.name)
            existing_id = self._identity.get(identity)
            if existing_id is not None:
                existing = self._targets[existing_id]
                existing_create = AnalysisTargetCreate.model_validate(existing.model_dump())
                if _canonical_create(existing_create) != _canonical_create(value):
                    raise DuplicateTarget(identity)
                return existing.model_copy(deep=True)
            target = AnalysisTarget(**value.model_dump())
            self._targets[target.id] = target
            self._identity[identity] = target.id
            return target.model_copy(deep=True)

    def get_target(self, target_id: UUID, tenant_id: UUID) -> AnalysisTarget:
        with self._lock:
            target = self._targets.get(target_id)
            if target is None or target.tenant_id != tenant_id:
                raise NotFound(target_id)
            return target.model_copy(deep=True)

    def list_targets(self, tenant_id: UUID, *, limit: int = 100) -> tuple[AnalysisTarget, ...]:
        with self._lock:
            values = sorted(
                (item for item in self._targets.values() if item.tenant_id == tenant_id),
                key=lambda item: (item.created_at, str(item.id)),
                reverse=True,
            )
            return tuple(item.model_copy(deep=True) for item in values[:limit])

    def set_target_state(
        self, target_id: UUID, tenant_id: UUID, expected_revision: int, state: TargetState
    ) -> AnalysisTarget:
        with self._lock:
            target = self._targets.get(target_id)
            if target is None or target.tenant_id != tenant_id:
                raise NotFound(target_id)
            if target.revision != expected_revision:
                raise RevisionConflict(target_id)
            updated = target.model_copy(update={"state": state, "revision": target.revision + 1})
            self._targets[target_id] = updated
            return updated.model_copy(deep=True)


class PostgresRepository:
    """Transactional PostgreSQL adapter. Tenant rows must be provisioned separately."""

    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and not database_url:
            raise ValueError("database_url is required")
        if database_url and database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self._engine = engine or create_engine(database_url, pool_pre_ping=True)

    @contextmanager
    def _transaction(self, *, serializable: bool = False) -> Iterator:
        connection = self._engine.connect()
        if serializable:
            connection = connection.execution_options(isolation_level="SERIALIZABLE")
        transaction = connection.begin()
        try:
            yield connection
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _decode(row) -> AnalysisTarget:
        permissions = row.permissions_json
        evidence = row.source_evidence_ids_json
        if isinstance(permissions, str):
            permissions = json.loads(permissions)
        if isinstance(evidence, str):
            evidence = json.loads(evidence)
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return AnalysisTarget(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            target_type=row.target_type,
            classification=row.classification,
            permissions=permissions,
            source_evidence_ids=evidence,
            state=row.state,
            revision=row.revision,
            created_at=created_at.astimezone(UTC),
        )

    def provision_tenant(self, tenant_id: UUID, name: str) -> None:
        """Provisioning hook for an operator-controlled tenant lifecycle."""
        with self._transaction() as connection:
            connection.execute(
                text("INSERT INTO tenants (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"),
                {"id": tenant_id, "name": name},
            )

    def create_target(self, value: AnalysisTargetCreate) -> AnalysisTarget:
        canonical = _canonical_create(value)
        target = AnalysisTarget(**value.model_dump())
        params = {
            "id": target.id,
            "tenant_id": value.tenant_id,
            "name": value.name,
            "target_type": value.target_type.value,
            "classification": value.classification.value,
            "permissions": json.dumps(value.permissions.model_dump(), sort_keys=True, separators=(",", ":")),
            "evidence": json.dumps([str(item) for item in value.source_evidence_ids], separators=(",", ":")),
            "request_fingerprint": canonical,
        }
        try:
            # READ COMMITTED plus the unique constraint makes concurrent retries converge:
            # a competing insert waits, then the losing request reads the committed row.
            with self._transaction() as connection:
                row = connection.execute(
                    text("""
                        INSERT INTO analysis_targets
                          (id, tenant_id, name, target_type, classification, state, revision,
                           permissions_json, source_evidence_ids_json, request_fingerprint, created_by)
                        VALUES
                          (:id, :tenant_id, :name, :target_type, :classification, 'DRAFT', 0,
                           CAST(:permissions AS jsonb), CAST(:evidence AS jsonb), :request_fingerprint, :tenant_id)
                        ON CONFLICT (tenant_id, name) DO NOTHING
                        RETURNING *
                    """),
                    params,
                ).first()
                if row is None:
                    row = connection.execute(
                        text("SELECT * FROM analysis_targets WHERE tenant_id=:tenant_id AND name=:name"),
                        params,
                    ).one()
                    if row.request_fingerprint != canonical:
                        raise DuplicateTarget((value.tenant_id, value.name))
                return self._decode(row)
        except IntegrityError as exc:
            raise NotFound(value.tenant_id) from exc

    def get_target(self, target_id: UUID, tenant_id: UUID) -> AnalysisTarget:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM analysis_targets WHERE id=:id AND tenant_id=:tenant_id"),
                {"id": target_id, "tenant_id": tenant_id},
            ).first()
        if row is None:
            raise NotFound(target_id)
        return self._decode(row)

    def list_targets(self, tenant_id: UUID, *, limit: int = 100) -> tuple[AnalysisTarget, ...]:
        safe_limit = max(1, min(limit, 100))
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM analysis_targets WHERE tenant_id=:tenant_id "
                     "ORDER BY created_at DESC,id DESC LIMIT :limit"),
                {"tenant_id": tenant_id, "limit": safe_limit},
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def set_target_state(
        self, target_id: UUID, tenant_id: UUID, expected_revision: int, state: TargetState
    ) -> AnalysisTarget:
        with self._transaction() as connection:
            row = connection.execute(
                text("""
                    UPDATE analysis_targets SET state=:state, revision=revision + 1
                    WHERE id=:id AND tenant_id=:tenant_id AND revision=:revision RETURNING *
                """),
                {"state": state.value, "id": target_id, "tenant_id": tenant_id, "revision": expected_revision},
            ).first()
            if row is not None:
                return self._decode(row)
            exists = connection.execute(
                text("SELECT revision FROM analysis_targets WHERE id=:id AND tenant_id=:tenant_id"),
                {"id": target_id, "tenant_id": tenant_id},
            ).first()
            if exists is None:
                raise NotFound(target_id)
            raise RevisionConflict(target_id)
