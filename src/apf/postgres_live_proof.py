"""PostgreSQL live proof harness: migrations, repository contract, and durable schema smoke."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .migrations import downgrade, migration_versions, upgrade
from .repository import PostgresRepository


class PostgresLiveProofRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProofStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class ProofCheckResult:
    check_id: str
    status: ProofStatus
    message: str


@dataclass(frozen=True)
class PostgresLiveProofReport:
    foundry_root: Path
    evaluated_at: datetime
    database_url_redacted: str
    results: tuple[ProofCheckResult, ...]
    overall: ProofStatus
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.postgres-live-proof-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "database_url_redacted": self.database_url_redacted,
            "overall": self.overall.value,
            "report_digest": self.report_digest,
            "results": [
                {"check_id": item.check_id, "status": item.status.value, "message": item.message}
                for item in self.results
            ],
        }


def resolve_database_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


def redact_database_url(url: str) -> str:
    if "@" not in url:
        return url.split("://", 1)[0] + "://***"
    prefix, suffix = url.split("@", 1)
    scheme = prefix.split("://", 1)[0]
    return f"{scheme}://***@{suffix}"


def _contract_smoke(repository: PostgresRepository, tenant_id) -> None:
    from .domain import (
        AnalysisTargetCreate,
        Classification,
        ScopePermissions,
        TargetState,
        TargetType,
    )

    repository.provision_tenant(tenant_id, f"tenant-{tenant_id}")
    value = AnalysisTargetCreate(
        tenant_id=tenant_id,
        name="live-proof",
        target_type=TargetType.OWNED_SYSTEM,
        classification=Classification.INTERNAL,
        permissions=ScopePermissions(read=True, parse=True, derive=True),
        source_evidence_ids=[uuid4()],
    )
    created = repository.create_target(value)
    if repository.get_target(created.id, tenant_id).id != created.id:
        raise PostgresLiveProofRejected("GET_TARGET", "tenant-scoped get failed")
    moved = repository.set_target_state(created.id, tenant_id, 0, TargetState.AUTHORIZATION_PENDING)
    if moved.revision != 1:
        raise PostgresLiveProofRejected("CAS_REVISION", "optimistic revision update failed")
    duplicate = repository.create_target(value)
    if duplicate.id != created.id:
        raise PostgresLiveProofRejected("IDEMPOTENCY", "idempotent create did not converge")


def _durable_schema_smoke(engine: Engine) -> None:
    versions = migration_versions()
    if "0003_durable_review" not in versions:
        raise PostgresLiveProofRejected("MIGRATION_MISSING", "0003_durable_review migration not packaged")
    tenant_id = str(uuid4())
    job_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO durable_jobs (tenant_id, job_id, principal_id, request_fingerprint, "
                "job_fingerprint, idempotency_key, create_payload_fingerprint, state, version, "
                "event_head, event_count, expires_at, snapshot_hash, quarantined) "
                "VALUES (:tenant_id, :job_id, :principal_id, :request_fingerprint, :job_fingerprint, "
                ":idempotency_key, :create_payload_fingerprint, :state, :version, :event_head, "
                ":event_count, now() + interval '1 hour', :snapshot_hash, false)"
            ),
            {
                "tenant_id": tenant_id,
                "job_id": job_id,
                "principal_id": str(uuid4()),
                "request_fingerprint": "sha256:" + "a" * 64,
                "job_fingerprint": "sha256:" + "b" * 64,
                "idempotency_key": str(uuid4()),
                "create_payload_fingerprint": "sha256:" + "c" * 64,
                "state": "CREATED",
                "version": 0,
                "event_head": "sha256:" + "d" * 64,
                "event_count": 0,
                "snapshot_hash": "sha256:" + "e" * 64,
            },
        )
        row = connection.execute(
            text("SELECT tenant_id, job_id FROM durable_jobs WHERE tenant_id=:tenant_id AND job_id=:job_id"),
            {"tenant_id": tenant_id, "job_id": job_id},
        ).one()
        if row.tenant_id != tenant_id:
            raise PostgresLiveProofRejected("DURABLE_SMOKE", "durable_jobs round-trip failed")


class PostgresLiveProofHarness:
    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.store_root = self.foundry_root / "state" / "postgres-live-proof"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def run(self, *, now: datetime | None = None, dry_run: bool = False) -> PostgresLiveProofReport:
        evaluated_at = now or datetime.now(tz=UTC)
        if evaluated_at.tzinfo is None:
            raise PostgresLiveProofRejected("TIMESTAMP", "timezone-aware timestamp required")
        database_url = resolve_database_url()
        if not database_url:
            results = (
                ProofCheckResult(
                    "DATABASE_URL",
                    ProofStatus.SKIP,
                    "TEST_DATABASE_URL or DATABASE_URL not configured; live proof not run",
                ),
            )
            return self._finalize(evaluated_at, "***", results, dry_run=dry_run)
        engine = create_engine(database_url, pool_pre_ping=True)
        results: list[ProofCheckResult] = []
        try:
            reverted = downgrade(engine)
            results.append(
                ProofCheckResult("MIGRATION_DOWNGRADE", ProofStatus.PASS, f"reverted {reverted or 'none'}")
            )
            applied = upgrade(engine)
            results.append(
                ProofCheckResult("MIGRATION_UPGRADE", ProofStatus.PASS, f"applied {applied}")
            )
            repository = PostgresRepository(engine=engine)
            tenant_id = uuid4()
            _contract_smoke(repository, tenant_id)
            results.append(
                ProofCheckResult("REPOSITORY_CONTRACT", ProofStatus.PASS, "tenant-scoped contract smoke passed")
            )
            _durable_schema_smoke(engine)
            results.append(
                ProofCheckResult("DURABLE_SCHEMA", ProofStatus.PASS, "durable_jobs insert/select passed")
            )
        except (SQLAlchemyError, OSError, RuntimeError, PostgresLiveProofRejected) as error:
            results.append(
                ProofCheckResult(
                    "POSTGRES_LIVE_PROOF",
                    ProofStatus.FAIL,
                    str(getattr(error, "code", None) or error),
                )
            )
        finally:
            engine.dispose()
        return self._finalize(evaluated_at, redact_database_url(database_url), tuple(results), dry_run=dry_run)

    def _finalize(
        self,
        evaluated_at: datetime,
        database_url_redacted: str,
        results: tuple[ProofCheckResult, ...],
        *,
        dry_run: bool,
    ) -> PostgresLiveProofReport:
        overall = (
            ProofStatus.FAIL
            if any(item.status is ProofStatus.FAIL for item in results)
            else ProofStatus.SKIP
            if results and all(item.status is ProofStatus.SKIP for item in results)
            else ProofStatus.PASS
        )
        document = {
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": evaluated_at.isoformat(),
            "database_url_redacted": database_url_redacted,
            "overall": overall.value,
            "results": [item.__dict__ for item in results],
        }
        digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        report = PostgresLiveProofReport(
            foundry_root=self.foundry_root,
            evaluated_at=evaluated_at,
            database_url_redacted=database_url_redacted,
            results=results,
            overall=overall,
            report_digest=digest,
        )
        if not dry_run:
            target = self.store_root / f"{evaluated_at.strftime('%Y-%m-%d')}-{digest[:16]}.json"
            target.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        if overall is ProofStatus.FAIL:
            raise PostgresLiveProofRejected("POSTGRES_LIVE_PROOF_FAILED", "postgres live proof checks failed")
        return report
