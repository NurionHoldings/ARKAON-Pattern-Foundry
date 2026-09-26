"""PostgreSQL durable review adapter — ConsoleReviewStore over durable_jobs/review_tasks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from .acquisition_orchestrator import AcquisitionJob, JobState
from .durable_review import (
    DurableJobRecord,
    DurableStoreError,
    ReviewAttestation,
    ReviewDecision,
    ReviewStage,
    ReviewStatus,
    ReviewTask,
    _attestation_bytes,
    _hash,
    _parse_time,
)


class PostgresDurableReviewRepository:
    """Minimal PostgreSQL-backed durable review store for live CI proof."""

    def __init__(
        self,
        engine: Engine,
        *,
        ethernian_public_key: Ed25519PublicKey,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._key = ethernian_public_key
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def create_job(self, job: AcquisitionJob) -> DurableJobRecord:
        job.verify_ledger()
        request = job.request
        create_fp = request.request_fingerprint
        expiry = min(
            request.material_request.expires_at,
            request.auth_request.expires_at if request.auth_request else request.material_request.expires_at,
        )
        record = DurableJobRecord(
            request.tenant_id,
            str(request.job_id),
            request.principal_id,
            request.request_fingerprint,
            request.job_fingerprint,
            request.idempotency_key,
            job.state,
            job.version,
            job.events[-1].event_hash,
            len(job.events),
            expiry,
        )
        with self._engine.begin() as connection:
            prior = connection.execute(
                text(
                    "SELECT job_id, create_payload_fingerprint FROM durable_jobs "
                    "WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key"
                ),
                {"tenant_id": record.tenant_id, "idempotency_key": record.idempotency_key},
            ).mappings().first()
            if prior:
                if prior["create_payload_fingerprint"] != create_fp:
                    raise DurableStoreError("IDEMPOTENCY_CONFLICT")
                return self.load_job(record.tenant_id, prior["job_id"])
            connection.execute(
                text(
                    "INSERT INTO durable_jobs VALUES "
                    "(:tenant_id,:job_id,:principal_id,:request_fingerprint,:job_fingerprint,"
                    ":idempotency_key,:create_payload_fingerprint,:state,:version,:event_head,"
                    ":event_count,:expires_at,:snapshot_hash,false)"
                ),
                {
                    "tenant_id": record.tenant_id,
                    "job_id": record.job_id,
                    "principal_id": record.principal_id,
                    "request_fingerprint": record.request_fingerprint,
                    "job_fingerprint": record.job_fingerprint,
                    "idempotency_key": record.idempotency_key,
                    "create_payload_fingerprint": create_fp,
                    "state": record.state.value,
                    "version": record.version,
                    "event_head": record.event_head,
                    "event_count": record.event_count,
                    "expires_at": record.expires_at,
                    "snapshot_hash": self._snapshot_hash(record),
                },
            )
            for event in job.events:
                connection.execute(
                    text(
                        "INSERT INTO durable_events VALUES "
                        "(:tenant_id,:job_id,:sequence,:job_fingerprint,:event_type,:state,"
                        ":version,:occurred_at,CAST(:metadata AS jsonb),:previous_hash,:event_hash)"
                    ),
                    {
                        "tenant_id": record.tenant_id,
                        "job_id": record.job_id,
                        "sequence": event.sequence,
                        "job_fingerprint": event.job_fingerprint,
                        "event_type": event.event_type,
                        "state": event.state.value,
                        "version": event.version,
                        "occurred_at": event.timestamp,
                        "metadata": json.dumps(dict(event.metadata), sort_keys=True),
                        "previous_hash": event.previous_hash,
                        "event_hash": event.event_hash,
                    },
                )
        return record

    def load_job(self, tenant_id: str, job_id: str) -> DurableJobRecord:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM durable_jobs WHERE tenant_id=:tenant_id AND job_id=:job_id"),
                {"tenant_id": tenant_id, "job_id": job_id},
            ).mappings().one()
        record = DurableJobRecord(
            row["tenant_id"],
            row["job_id"],
            row["principal_id"],
            row["request_fingerprint"],
            row["job_fingerprint"],
            row["idempotency_key"],
            JobState(row["state"]),
            row["version"],
            row["event_head"],
            row["event_count"],
            row["expires_at"].astimezone(UTC) if hasattr(row["expires_at"], "astimezone") else _parse_time(str(row["expires_at"])),
            bool(row["quarantined"]),
        )
        if row["snapshot_hash"] != self._snapshot_hash(record):
            raise DurableStoreError("SNAPSHOT_INTEGRITY_FAILURE")
        return record

    def create_review(
        self,
        tenant_id: str,
        job_id: str,
        *,
        stage: ReviewStage,
        reason_code: str,
        evidence_fingerprint: str,
        expires_at: datetime,
    ) -> ReviewTask:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", reason_code):
            raise DurableStoreError("INVALID_REASON_CODE")
        job = self.load_job(tenant_id, job_id)
        task = ReviewTask(
            str(uuid4()),
            tenant_id,
            job_id,
            job.request_fingerprint,
            job.principal_id,
            stage,
            reason_code,
            evidence_fingerprint,
            expires_at,
        )
        task_hash = _hash(
            {
                "event_head": job.event_head,
                "job_fingerprint": job.job_fingerprint,
                "task_fingerprint": task.fingerprint,
            }
        )
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO review_tasks VALUES "
                    "(:tenant_id,:task_id,:job_id,:request_fingerprint,:principal_id,:stage,"
                    ":reason_code,:evidence_fingerprint,:expires_at,:status,NULL,NULL,NULL,NULL,"
                    ":job_event_head,:task_hash)"
                ),
                {
                    "tenant_id": task.tenant_id,
                    "task_id": task.task_id,
                    "job_id": task.job_id,
                    "request_fingerprint": task.request_fingerprint,
                    "principal_id": task.principal_id,
                    "stage": task.stage.value,
                    "reason_code": task.reason_code,
                    "evidence_fingerprint": task.evidence_fingerprint,
                    "expires_at": task.expires_at,
                    "status": task.status.value,
                    "job_event_head": job.event_head,
                    "task_hash": task_hash,
                },
            )
        return task

    def list_reviews_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[ReviewTask, ...]:
        if not 1 <= limit <= 100 or offset < 0:
            raise DurableStoreError("INVALID_PAGE")
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM review_tasks WHERE tenant_id=:tenant_id AND principal_id=:principal_id "
                    "ORDER BY expires_at, task_id LIMIT :limit OFFSET :offset"
                ),
                {"tenant_id": tenant_id, "principal_id": principal_id, "limit": limit, "offset": offset},
            ).mappings().all()
        return tuple(self._task(row) for row in rows)

    def get_review_for_principal(self, tenant_id: str, principal_id: str, task_id: str) -> ReviewTask:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT * FROM review_tasks WHERE tenant_id=:tenant_id AND principal_id=:principal_id "
                    "AND task_id=:task_id"
                ),
                {"tenant_id": tenant_id, "principal_id": principal_id, "task_id": task_id},
            ).mappings().first()
        if row is None:
            raise DurableStoreError("REVIEW_NOT_FOUND")
        return self._task(row)

    def count_reviews_for_principal(self, tenant_id: str, principal_id: str) -> int:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT COUNT(*) AS total FROM review_tasks "
                    "WHERE tenant_id=:tenant_id AND principal_id=:principal_id"
                ),
                {"tenant_id": tenant_id, "principal_id": principal_id},
            ).mappings().one()
        return int(row["total"])

    def count_candidates_for_principal(self, tenant_id: str, principal_id: str) -> int:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT COUNT(*) AS total FROM candidate_manifests c JOIN durable_jobs j "
                    "ON j.tenant_id=c.tenant_id AND j.job_id=c.job_id "
                    "WHERE c.tenant_id=:tenant_id AND j.principal_id=:principal_id"
                ),
                {"tenant_id": tenant_id, "principal_id": principal_id},
            ).mappings().one()
        return int(row["total"])

    def list_candidate_manifests_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[dict[str, Any], ...]:
        return ()

    def decide_review(self, tenant_id: str, task_id: str, attestation: ReviewAttestation) -> ReviewTask:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("SELECT * FROM review_tasks WHERE tenant_id=:tenant_id AND task_id=:task_id FOR UPDATE"),
                {"tenant_id": tenant_id, "task_id": task_id},
            ).mappings().one()
            task = self._task(row)
            if task.status is not ReviewStatus.OPEN:
                raise DurableStoreError("REVIEW_ALREADY_CLOSED")
            if self._now() >= task.expires_at:
                connection.execute(
                    text(
                        "UPDATE review_tasks SET status='EXPIRED' WHERE tenant_id=:tenant_id AND task_id=:task_id"
                    ),
                    {"tenant_id": tenant_id, "task_id": task_id},
                )
                raise DurableStoreError("REVIEW_EXPIRED")
            try:
                self._key.verify(bytes.fromhex(attestation.signature), _attestation_bytes(attestation))
            except (InvalidSignature, ValueError, TypeError):
                raise DurableStoreError("INVALID_REVIEW_SIGNATURE") from None
            status = ReviewStatus.APPROVED if attestation.decision is ReviewDecision.APPROVE else ReviewStatus.DENIED
            try:
                changed = connection.execute(
                    text(
                        "UPDATE review_tasks SET status=:status, decision_nonce=:nonce, decision=:decision, "
                        "decision_expires_at=:expires_at, decision_signature=:signature "
                        "WHERE tenant_id=:tenant_id AND task_id=:task_id AND status='OPEN'"
                    ),
                    {
                        "status": status.value,
                        "nonce": attestation.nonce,
                        "decision": attestation.decision.value,
                        "expires_at": attestation.expires_at,
                        "signature": attestation.signature,
                        "tenant_id": tenant_id,
                        "task_id": task_id,
                    },
                ).rowcount
            except IntegrityError:
                raise DurableStoreError("REVIEW_NONCE_REPLAY") from None
            if changed != 1:
                raise DurableStoreError("REVIEW_ALREADY_CLOSED")
        return replace(task, status=status)

    @staticmethod
    def _snapshot_hash(record: DurableJobRecord) -> str:
        return _hash(
            {
                "event_count": record.event_count,
                "event_head": record.event_head,
                "job_fingerprint": record.job_fingerprint,
                "job_id": record.job_id,
                "request_fingerprint": record.request_fingerprint,
                "state": record.state.value,
                "tenant_id": record.tenant_id,
                "version": record.version,
            }
        )

    def _now(self) -> datetime:
        value = self._now_provider()
        if value.tzinfo is None:
            raise DurableStoreError("NAIVE_CLOCK")
        return value.astimezone(UTC)

    @staticmethod
    def _task(row: Any) -> ReviewTask:
        expires = row["expires_at"]
        if hasattr(expires, "astimezone"):
            expires = expires.astimezone(UTC)
        else:
            expires = _parse_time(str(expires))
        return ReviewTask(
            row["task_id"],
            row["tenant_id"],
            row["job_id"],
            row["request_fingerprint"],
            row["principal_id"],
            ReviewStage(row["stage"]),
            row["reason_code"],
            row["evidence_fingerprint"],
            expires,
            ReviewStatus(row["status"]),
        )
