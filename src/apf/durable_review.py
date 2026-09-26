from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .acquisition_orchestrator import AcquisitionJob, JobState
from .learning_safety import scan_learning_text


class DurableStoreError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReviewStage(StrEnum):
    RIGHTS = "RIGHTS"
    COLLECTION = "COLLECTION"
    ORIGINALITY = "ORIGINALITY"


class ReviewStatus(StrEnum):
    OPEN = "OPEN"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    DENY = "DENY"


_DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_OPAQUE_REF = re.compile(r"\Aquarantine:[0-9a-f-]{36}\Z")
_NONCE = re.compile(r"\A[0-9a-f-]{36}\Z")
_FORBIDDEN_KEY = re.compile(
    r"(?i)(raw|body|dom|har|source.?map|password|passwd|token|cookie|session|authorization|secret)"
)


def _time(value: datetime) -> str:
    if value.tzinfo is None:
        raise DurableStoreError("NAIVE_TIMESTAMP")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise DurableStoreError("NAIVE_TIMESTAMP")
    return parsed.astimezone(UTC)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return "sha256:" + sha256(_json(value).encode()).hexdigest()


def _safe_text(value: str) -> None:
    if scan_learning_text(value):
        raise DurableStoreError("SECRET_OR_PII_BLOCKED")


def _safe_metadata(value: dict[str, str]) -> None:
    for key, item in value.items():
        if _FORBIDDEN_KEY.search(key):
            raise DurableStoreError("FORBIDDEN_PERSISTED_FIELD")
        _safe_text(item)
        if key.endswith(("hash", "fingerprint")):
            if not _DIGEST.fullmatch(item):
                raise DurableStoreError("INVALID_DIGEST")
        elif key.endswith("reference") and not _OPAQUE_REF.fullmatch(item):
            raise DurableStoreError("INVALID_OPAQUE_REFERENCE")


@dataclass(frozen=True)
class DurableJobRecord:
    tenant_id: str
    job_id: str
    principal_id: str
    request_fingerprint: str
    job_fingerprint: str
    idempotency_key: str
    state: JobState
    version: int
    event_head: str
    event_count: int
    expires_at: datetime
    quarantined: bool = False


@dataclass(frozen=True)
class ReviewTask:
    task_id: str
    tenant_id: str
    job_id: str
    request_fingerprint: str
    principal_id: str
    stage: ReviewStage
    reason_code: str
    evidence_fingerprint: str
    expires_at: datetime
    status: ReviewStatus = ReviewStatus.OPEN

    @property
    def fingerprint(self) -> str:
        return _hash({
            "evidence_fingerprint": self.evidence_fingerprint,
            "expires_at": _time(self.expires_at),
            "job_id": self.job_id,
            "principal_id": self.principal_id,
            "reason_code": self.reason_code,
            "request_fingerprint": self.request_fingerprint,
            "stage": self.stage.value,
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
        })


@dataclass(frozen=True)
class ReviewAttestation:
    task_fingerprint: str
    task_id: str
    job_id: str
    request_fingerprint: str
    tenant_id: str
    principal_id: str
    stage: ReviewStage
    evidence_fingerprint: str
    decision: ReviewDecision
    expires_at: datetime
    nonce: str
    signature: str


class ReviewSigner:
    """External Ethernian helper. DurableReviewRepository receives only a public key."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key

    def sign(
        self, task: ReviewTask, decision: ReviewDecision, *, expires_at: datetime, nonce: str
    ) -> ReviewAttestation:
        unsigned = ReviewAttestation(
            task.fingerprint, task.task_id, task.job_id, task.request_fingerprint,
            task.tenant_id, task.principal_id, task.stage, task.evidence_fingerprint,
            decision, expires_at, nonce, "",
        )
        signature = self._key.sign(_attestation_bytes(unsigned)).hex()
        return ReviewAttestation(**{**asdict(unsigned), "signature": signature})


def _attestation_bytes(item: ReviewAttestation) -> bytes:
    data = asdict(item)
    data["stage"] = item.stage.value
    data["decision"] = item.decision.value
    data["expires_at"] = _time(item.expires_at)
    data["signature"] = ""
    return _json(data).encode()


class DurableReviewRepository:
    """SQLite durability boundary; intentionally persists no captured material."""

    def __init__(
        self, path: str | Path, *, ethernian_public_key: Ed25519PublicKey,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = str(path)
        self._key = ethernian_public_key
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._migrate()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    def _now(self) -> datetime:
        value = self._now_provider()
        if value.tzinfo is None:
            raise DurableStoreError("NAIVE_CLOCK")
        return value.astimezone(UTC)

    def _migrate(self) -> None:
        with self._connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO schema_migrations VALUES(1);
            CREATE TABLE IF NOT EXISTS durable_jobs(
              tenant_id TEXT NOT NULL, job_id TEXT NOT NULL, principal_id TEXT NOT NULL,
              request_fingerprint TEXT NOT NULL, job_fingerprint TEXT NOT NULL,
              idempotency_key TEXT NOT NULL, create_payload_fingerprint TEXT NOT NULL,
              state TEXT NOT NULL, version INTEGER NOT NULL, event_head TEXT NOT NULL,
              event_count INTEGER NOT NULL, expires_at TEXT NOT NULL,
              snapshot_hash TEXT NOT NULL, quarantined INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(tenant_id, job_id), UNIQUE(tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS durable_events(
              tenant_id TEXT NOT NULL, job_id TEXT NOT NULL, sequence INTEGER NOT NULL,
              job_fingerprint TEXT NOT NULL, event_type TEXT NOT NULL, state TEXT NOT NULL,
              version INTEGER NOT NULL, occurred_at TEXT NOT NULL, metadata TEXT NOT NULL,
              previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
              PRIMARY KEY(tenant_id, job_id, sequence), UNIQUE(tenant_id, job_id, event_hash),
              FOREIGN KEY(tenant_id, job_id) REFERENCES durable_jobs(tenant_id, job_id)
            );
            CREATE TABLE IF NOT EXISTS command_receipts(
              tenant_id TEXT NOT NULL, job_id TEXT NOT NULL, command_id TEXT NOT NULL,
              payload_fingerprint TEXT NOT NULL, resulting_state TEXT NOT NULL,
              resulting_version INTEGER NOT NULL, event_hash TEXT NOT NULL, receipt_hash TEXT NOT NULL,
              PRIMARY KEY(tenant_id, job_id, command_id)
            );
            CREATE TABLE IF NOT EXISTS review_tasks(
              tenant_id TEXT NOT NULL, task_id TEXT NOT NULL, job_id TEXT NOT NULL,
              request_fingerprint TEXT NOT NULL, principal_id TEXT NOT NULL, stage TEXT NOT NULL,
              reason_code TEXT NOT NULL, evidence_fingerprint TEXT NOT NULL,
              expires_at TEXT NOT NULL, status TEXT NOT NULL, decision_nonce TEXT,
              decision TEXT, decision_expires_at TEXT, decision_signature TEXT,
              job_event_head TEXT NOT NULL, task_hash TEXT NOT NULL,
              PRIMARY KEY(tenant_id, task_id),
              FOREIGN KEY(tenant_id, job_id) REFERENCES durable_jobs(tenant_id, job_id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_review_nonce
              ON review_tasks(decision_nonce) WHERE decision_nonce IS NOT NULL;
            CREATE TABLE IF NOT EXISTS candidate_manifests(
              tenant_id TEXT NOT NULL, job_id TEXT NOT NULL, candidate_hash TEXT NOT NULL,
              quarantine_reference TEXT NOT NULL, license_obligations TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status='CANDIDATE_NOT_OWNED_ASSET'),
              job_event_head TEXT NOT NULL, manifest_hash TEXT NOT NULL,
              PRIMARY KEY(tenant_id, job_id),
              FOREIGN KEY(tenant_id, job_id) REFERENCES durable_jobs(tenant_id, job_id)
            );
            """)

    @staticmethod
    def _snapshot_hash(record: DurableJobRecord) -> str:
        return _hash({
            "event_count": record.event_count, "event_head": record.event_head,
            "job_fingerprint": record.job_fingerprint, "job_id": record.job_id,
            "request_fingerprint": record.request_fingerprint, "state": record.state.value,
            "tenant_id": record.tenant_id, "version": record.version,
        })

    def create_job(self, job: AcquisitionJob) -> DurableJobRecord:
        job.verify_ledger()
        request = job.request
        create_fp = request.request_fingerprint
        expiry = min(
            request.material_request.expires_at,
            request.auth_request.expires_at if request.auth_request else request.material_request.expires_at,
        )
        record = DurableJobRecord(
            request.tenant_id, str(request.job_id), request.principal_id,
            request.request_fingerprint, request.job_fingerprint, request.idempotency_key,
            job.state, job.version, job.events[-1].event_hash, len(job.events), expiry,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT job_id,create_payload_fingerprint FROM durable_jobs "
                "WHERE tenant_id=? AND idempotency_key=?",
                (record.tenant_id, record.idempotency_key),
            ).fetchone()
            if prior:
                if prior["create_payload_fingerprint"] != create_fp:
                    db.rollback()
                    raise DurableStoreError("IDEMPOTENCY_CONFLICT")
                db.commit()
                return self.load_job(record.tenant_id, prior["job_id"])
            db.execute(
                "INSERT INTO durable_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (record.tenant_id, record.job_id, record.principal_id,
                 record.request_fingerprint, record.job_fingerprint, record.idempotency_key,
                 create_fp, record.state.value, record.version, record.event_head,
                 record.event_count, _time(record.expires_at), self._snapshot_hash(record), 0),
            )
            self._insert_events(db, record.tenant_id, record.job_id, job.events)
            db.commit()
        return record

    def save_job(self, job: AcquisitionJob, *, expected_version: int) -> DurableJobRecord:
        job.verify_ledger()
        request = job.request
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT version,event_count,request_fingerprint,job_fingerprint,expires_at "
                "FROM durable_jobs WHERE tenant_id=? AND job_id=?",
                (request.tenant_id, str(request.job_id)),
            ).fetchone()
            if row is None:
                db.rollback()
                raise DurableStoreError("JOB_NOT_FOUND")
            if row["version"] != expected_version:
                db.rollback()
                raise DurableStoreError("STALE_VERSION")
            if (row["request_fingerprint"], row["job_fingerprint"]) != (
                request.request_fingerprint, request.job_fingerprint
            ):
                db.rollback()
                raise DurableStoreError("JOB_BINDING_MISMATCH")
            old_count = row["event_count"]
            self._insert_events(db, request.tenant_id, str(request.job_id), job.events[old_count:])
            record = DurableJobRecord(
                request.tenant_id, str(request.job_id), request.principal_id,
                request.request_fingerprint, request.job_fingerprint, request.idempotency_key,
                job.state, job.version, job.events[-1].event_hash, len(job.events),
                _parse_time(row["expires_at"]),
            )
            changed = db.execute(
                "UPDATE durable_jobs SET state=?,version=?,event_head=?,event_count=?,snapshot_hash=? "
                "WHERE tenant_id=? AND job_id=? AND version=?",
                (record.state.value, record.version, record.event_head, record.event_count,
                 self._snapshot_hash(record), record.tenant_id, record.job_id, expected_version),
            ).rowcount
            if changed != 1:
                db.rollback()
                raise DurableStoreError("STALE_VERSION")
            for receipt in job._receipts.values():
                prior = db.execute(
                    "SELECT payload_fingerprint FROM command_receipts "
                    "WHERE tenant_id=? AND job_id=? AND command_id=?",
                    (record.tenant_id, record.job_id, receipt.command_id),
                ).fetchone()
                if prior and prior[0] != receipt.payload_fingerprint:
                    db.rollback()
                    raise DurableStoreError("IDEMPOTENCY_CONFLICT")
                db.execute(
                    "INSERT OR IGNORE INTO command_receipts VALUES(?,?,?,?,?,?,?,?)",
                    (record.tenant_id, record.job_id, receipt.command_id,
                     receipt.payload_fingerprint, receipt.resulting_state.value,
                     receipt.resulting_version, receipt.event_hash,
                     self._receipt_hash(record, receipt.command_id, receipt.payload_fingerprint,
                                        receipt.resulting_state.value, receipt.resulting_version,
                                        receipt.event_hash)),
                )
            db.commit()
        return record

    @staticmethod
    def _insert_events(db: sqlite3.Connection, tenant: str, job_id: str, events: list[Any]) -> None:
        for event in events:
            _safe_metadata(dict(event.metadata))
            db.execute(
                "INSERT INTO durable_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (tenant, job_id, event.sequence, event.job_fingerprint, event.event_type,
                 event.state.value, event.version, _time(event.timestamp),
                 _json(dict(event.metadata)), event.previous_hash, event.event_hash),
            )

    def load_job(self, tenant_id: str, job_id: str) -> DurableJobRecord:
        _safe_text(tenant_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM durable_jobs WHERE tenant_id=? AND job_id=?", (tenant_id, job_id)
            ).fetchone()
            if row is None:
                raise DurableStoreError("JOB_NOT_FOUND")
            record = DurableJobRecord(
                row["tenant_id"], row["job_id"], row["principal_id"],
                row["request_fingerprint"], row["job_fingerprint"], row["idempotency_key"],
                JobState(row["state"]), row["version"], row["event_head"], row["event_count"],
                _parse_time(row["expires_at"]), bool(row["quarantined"]),
            )
            if row["snapshot_hash"] != self._snapshot_hash(record):
                raise DurableStoreError("SNAPSHOT_INTEGRITY_FAILURE")
            events = db.execute(
                "SELECT * FROM durable_events WHERE tenant_id=? AND job_id=? ORDER BY sequence",
                (tenant_id, job_id),
            ).fetchall()
            previous = "GENESIS"
            if len(events) != record.event_count:
                raise DurableStoreError("EVENT_CHAIN_INTEGRITY_FAILURE")
            for expected, event in enumerate(events, 1):
                metadata = json.loads(event["metadata"])
                _safe_metadata(metadata)
                body = {
                    "event_type": event["event_type"], "job_fingerprint": event["job_fingerprint"],
                    "metadata": metadata, "previous_hash": event["previous_hash"],
                    "sequence": event["sequence"], "state": event["state"],
                    "timestamp": _time(_parse_time(event["occurred_at"])),
                    "version": event["version"],
                }
                if (event["sequence"] != expected or event["previous_hash"] != previous
                        or event["job_fingerprint"] != record.job_fingerprint
                        or event["event_hash"] != _hash(body)):
                    raise DurableStoreError("EVENT_CHAIN_INTEGRITY_FAILURE")
                previous = event["event_hash"]
            if not events or previous != record.event_head:
                raise DurableStoreError("EVENT_CHAIN_INTEGRITY_FAILURE")
            if events[-1]["version"] != record.version or events[-1]["state"] != record.state.value:
                raise DurableStoreError("SNAPSHOT_EVENT_MISMATCH")
            self._expire_reviews(db, tenant_id, job_id)
            self._verify_receipts(db, record, events)
            self._verify_reviews(db, record)
            self._verify_candidate(db, record)
            return record

    @staticmethod
    def _receipt_hash(
        record: DurableJobRecord, command_id: str, payload_fingerprint: str,
        state: str, version: int, event_hash: str,
    ) -> str:
        return _hash({
            "command_id": command_id, "event_hash": event_hash,
            "job_fingerprint": record.job_fingerprint, "job_id": record.job_id,
            "payload_fingerprint": payload_fingerprint, "resulting_state": state,
            "resulting_version": version, "tenant_id": record.tenant_id,
        })

    @classmethod
    def _verify_receipts(
        cls, db: sqlite3.Connection, record: DurableJobRecord, events: list[sqlite3.Row]
    ) -> None:
        event_by_hash = {event["event_hash"]: event for event in events}
        rows = db.execute(
            "SELECT * FROM command_receipts WHERE tenant_id=? AND job_id=?",
            (record.tenant_id, record.job_id),
        ).fetchall()
        for receipt in rows:
            event = event_by_hash.get(receipt["event_hash"])
            if (event is None or event["version"] != receipt["resulting_version"]
                    or event["state"] != receipt["resulting_state"]
                    or not _DIGEST.fullmatch(receipt["payload_fingerprint"])
                    or json.loads(event["metadata"]).get("payload_fingerprint")
                    != receipt["payload_fingerprint"]
                    or receipt["receipt_hash"] != cls._receipt_hash(
                        record, receipt["command_id"], receipt["payload_fingerprint"],
                        receipt["resulting_state"], receipt["resulting_version"],
                        receipt["event_hash"],
                    )):
                raise DurableStoreError("RECEIPT_INTEGRITY_FAILURE")

    def _verify_reviews(self, db: sqlite3.Connection, record: DurableJobRecord) -> None:
        rows = db.execute(
            "SELECT * FROM review_tasks WHERE tenant_id=? AND job_id=?",
            (record.tenant_id, record.job_id),
        ).fetchall()
        for row in rows:
            task = self._task(row)
            if task.request_fingerprint != record.request_fingerprint or task.principal_id != record.principal_id:
                raise DurableStoreError("REVIEW_BINDING_MISMATCH")
            event_exists = db.execute(
                "SELECT 1 FROM durable_events WHERE tenant_id=? AND job_id=? AND event_hash=?",
                (record.tenant_id, record.job_id, row["job_event_head"]),
            ).fetchone()
            expected_task_hash = _hash({
                "event_head": row["job_event_head"], "job_fingerprint": record.job_fingerprint,
                "task_fingerprint": task.fingerprint,
            })
            if event_exists is None or row["task_hash"] != expected_task_hash:
                raise DurableStoreError("REVIEW_INTEGRITY_FAILURE")
            if task.status in {ReviewStatus.OPEN, ReviewStatus.EXPIRED}:
                if any(row[name] is not None for name in (
                    "decision_nonce", "decision", "decision_expires_at", "decision_signature"
                )):
                    raise DurableStoreError("REVIEW_INTEGRITY_FAILURE")
                continue
            if not all(row[name] is not None for name in (
                "decision_nonce", "decision", "decision_expires_at", "decision_signature"
            )):
                raise DurableStoreError("REVIEW_INTEGRITY_FAILURE")
            decision = ReviewDecision(row["decision"])
            expected_status = (
                ReviewStatus.APPROVED if decision is ReviewDecision.APPROVE else ReviewStatus.DENIED
            )
            if task.status is not expected_status:
                raise DurableStoreError("REVIEW_INTEGRITY_FAILURE")
            attestation = ReviewAttestation(
                task.fingerprint, task.task_id, task.job_id, task.request_fingerprint,
                task.tenant_id, task.principal_id, task.stage, task.evidence_fingerprint,
                decision, _parse_time(row["decision_expires_at"]), row["decision_nonce"],
                row["decision_signature"],
            )
            try:
                self._key.verify(
                    bytes.fromhex(attestation.signature), _attestation_bytes(attestation)
                )
            except (InvalidSignature, ValueError, TypeError):
                raise DurableStoreError("REVIEW_INTEGRITY_FAILURE") from None

    @staticmethod
    def _verify_candidate(db: sqlite3.Connection, record: DurableJobRecord) -> None:
        row = db.execute(
            "SELECT * FROM candidate_manifests WHERE tenant_id=? AND job_id=?",
            (record.tenant_id, record.job_id),
        ).fetchone()
        if row is None:
            return
        expected = _hash({
            "candidate_hash": row["candidate_hash"], "event_head": row["job_event_head"],
            "job_fingerprint": record.job_fingerprint, "job_id": record.job_id,
            "license_obligations": json.loads(row["license_obligations"]),
            "quarantine_reference": row["quarantine_reference"], "status": row["status"],
            "tenant_id": record.tenant_id,
        })
        event_exists = db.execute(
            "SELECT 1 FROM durable_events WHERE tenant_id=? AND job_id=? AND event_hash=?",
            (record.tenant_id, record.job_id, row["job_event_head"]),
        ).fetchone()
        if (event_exists is None or row["status"] != "CANDIDATE_NOT_OWNED_ASSET"
                or row["manifest_hash"] != expected):
            raise DurableStoreError("CANDIDATE_INTEGRITY_FAILURE")

    def create_review(
        self, tenant_id: str, job_id: str, *, stage: ReviewStage, reason_code: str,
        evidence_fingerprint: str, expires_at: datetime,
    ) -> ReviewTask:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", reason_code):
            raise DurableStoreError("INVALID_REASON_CODE")
        if not _DIGEST.fullmatch(evidence_fingerprint) or self._now() >= expires_at:
            raise DurableStoreError("INVALID_REVIEW_EVIDENCE")
        job = self.load_job(tenant_id, job_id)
        task = ReviewTask(
            str(uuid4()), tenant_id, job_id, job.request_fingerprint, job.principal_id,
            stage, reason_code, evidence_fingerprint, expires_at,
        )
        with self._connect() as db:
            task_hash = _hash({
                "event_head": job.event_head, "job_fingerprint": job.job_fingerprint,
                "task_fingerprint": task.fingerprint,
            })
            db.execute(
                "INSERT INTO review_tasks VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,?,?)",
                (task.tenant_id, task.task_id, task.job_id, task.request_fingerprint,
                 task.principal_id, task.stage.value, task.reason_code,
                 task.evidence_fingerprint, _time(task.expires_at), task.status.value,
                 job.event_head, task_hash),
            )
        return task

    def decide_review(self, tenant_id: str, task_id: str, attestation: ReviewAttestation) -> ReviewTask:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM review_tasks WHERE tenant_id=? AND task_id=?", (tenant_id, task_id)
            ).fetchone()
            if row is None:
                db.rollback()
                raise DurableStoreError("REVIEW_NOT_FOUND")
            task = self._task(row)
            if task.status is not ReviewStatus.OPEN:
                db.rollback()
                raise DurableStoreError("REVIEW_ALREADY_CLOSED")
            if self._now() >= task.expires_at:
                db.execute(
                    "UPDATE review_tasks SET status='EXPIRED' WHERE tenant_id=? AND task_id=?",
                    (tenant_id, task_id),
                )
                db.commit()
                raise DurableStoreError("REVIEW_EXPIRED")
            actual = (
                attestation.task_fingerprint, attestation.task_id, attestation.job_id,
                attestation.request_fingerprint, attestation.tenant_id, attestation.principal_id,
                attestation.stage, attestation.evidence_fingerprint,
            )
            expected = (
                task.fingerprint, task.task_id, task.job_id, task.request_fingerprint,
                task.tenant_id, task.principal_id, task.stage, task.evidence_fingerprint,
            )
            if actual != expected or not _NONCE.fullmatch(attestation.nonce):
                db.rollback()
                raise DurableStoreError("REVIEW_BINDING_MISMATCH")
            if attestation.expires_at.tzinfo is None or self._now() >= attestation.expires_at:
                db.rollback()
                raise DurableStoreError("REVIEW_ATTESTATION_EXPIRED")
            if attestation.expires_at > task.expires_at:
                db.rollback()
                raise DurableStoreError("REVIEW_EXPIRY_OUT_OF_BOUNDS")
            try:
                self._key.verify(bytes.fromhex(attestation.signature), _attestation_bytes(attestation))
            except (InvalidSignature, ValueError, TypeError):
                db.rollback()
                raise DurableStoreError("INVALID_REVIEW_SIGNATURE") from None
            status = (ReviewStatus.APPROVED if attestation.decision is ReviewDecision.APPROVE
                      else ReviewStatus.DENIED)
            try:
                changed = db.execute(
                    "UPDATE review_tasks SET status=?,decision_nonce=?,decision=?,"
                    "decision_expires_at=?,decision_signature=? "
                    "WHERE tenant_id=? AND task_id=? AND status='OPEN'",
                    (status.value, attestation.nonce, attestation.decision.value,
                     _time(attestation.expires_at), attestation.signature, tenant_id, task_id),
                ).rowcount
            except sqlite3.IntegrityError:
                db.rollback()
                raise DurableStoreError("REVIEW_NONCE_REPLAY") from None
            if changed != 1:
                db.rollback()
                raise DurableStoreError("REVIEW_ALREADY_CLOSED")
            db.commit()
            return ReviewTask(**{**asdict(task), "status": status})

    def list_open_reviews(self, tenant_id: str, job_id: str) -> tuple[ReviewTask, ...]:
        self.load_job(tenant_id, job_id)
        with self._connect() as db:
            self._expire_reviews(db, tenant_id, job_id)
            rows = db.execute(
                "SELECT * FROM review_tasks WHERE tenant_id=? AND job_id=? AND status='OPEN' "
                "ORDER BY expires_at,task_id", (tenant_id, job_id),
            ).fetchall()
            return tuple(self._task(row) for row in rows)

    def get_review_for_principal(self, tenant_id: str, principal_id: str, task_id: str) -> ReviewTask:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM review_tasks WHERE tenant_id=? AND principal_id=? AND task_id=?",
                (tenant_id, principal_id, task_id),
            ).fetchone()
        if row is None:
            raise DurableStoreError("REVIEW_NOT_FOUND")
        return self._task(row)

    def count_reviews_for_principal(self, tenant_id: str, principal_id: str) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS total FROM review_tasks WHERE tenant_id=? AND principal_id=?",
                (tenant_id, principal_id),
            ).fetchone()
        return int(row["total"])

    def count_candidates_for_principal(self, tenant_id: str, principal_id: str) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS total FROM candidate_manifests c JOIN durable_jobs j "
                "ON j.tenant_id=c.tenant_id AND j.job_id=c.job_id "
                "WHERE c.tenant_id=? AND j.principal_id=?",
                (tenant_id, principal_id),
            ).fetchone()
        return int(row["total"])

    def list_reviews_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[ReviewTask, ...]:
        """Return integrity-checked review metadata for one tenant principal."""
        if not 1 <= limit <= 100 or offset < 0:
            raise DurableStoreError("INVALID_PAGE")
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM review_tasks WHERE tenant_id=? AND principal_id=? "
                "ORDER BY expires_at,task_id LIMIT ? OFFSET ?",
                (tenant_id, principal_id, limit, offset),
            ).fetchall()
        for row in {item["job_id"]: item for item in rows}.values():
            self.load_job(tenant_id, row["job_id"])
        # load_job may atomically expire an OPEN task, so refetch the page before returning it.
        with self._connect() as db:
            current = db.execute(
                "SELECT * FROM review_tasks WHERE tenant_id=? AND principal_id=? "
                "ORDER BY expires_at,task_id LIMIT ? OFFSET ?",
                (tenant_id, principal_id, limit, offset),
            ).fetchall()
        return tuple(self._task(row) for row in current)

    def list_candidate_manifests_for_principal(
        self, tenant_id: str, principal_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[dict[str, Any], ...]:
        """Return safe, integrity-checked candidate manifest fields only."""
        if not 1 <= limit <= 100 or offset < 0:
            raise DurableStoreError("INVALID_PAGE")
        with self._connect() as db:
            rows = db.execute(
                "SELECT c.job_id FROM candidate_manifests c JOIN durable_jobs j "
                "ON j.tenant_id=c.tenant_id AND j.job_id=c.job_id "
                "WHERE c.tenant_id=? AND j.principal_id=? "
                "ORDER BY c.job_id LIMIT ? OFFSET ?",
                (tenant_id, principal_id, limit, offset),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            record = self.load_job(tenant_id, row["job_id"])
            manifest = self.get_candidate_manifest(tenant_id, row["job_id"])
            if manifest is not None:
                results.append({
                    "job_fingerprint": record.job_fingerprint,
                    "candidate_hash": manifest["candidate_hash"],
                    "license_obligations": tuple(json.loads(manifest["license_obligations"])),
                    "status": manifest["status"],
                })
        return tuple(results)

    def _expire_reviews(self, db: sqlite3.Connection, tenant_id: str, job_id: str) -> None:
        db.execute(
            "UPDATE review_tasks SET status='EXPIRED' WHERE tenant_id=? AND job_id=? "
            "AND status='OPEN' AND expires_at<=?", (tenant_id, job_id, _time(self._now())),
        )

    @staticmethod
    def _task(row: sqlite3.Row) -> ReviewTask:
        return ReviewTask(
            row["task_id"], row["tenant_id"], row["job_id"], row["request_fingerprint"],
            row["principal_id"], ReviewStage(row["stage"]), row["reason_code"],
            row["evidence_fingerprint"], _parse_time(row["expires_at"]), ReviewStatus(row["status"]),
        )

    def put_candidate_manifest(
        self, tenant_id: str, job_id: str, *, candidate_hash: str,
        quarantine_reference: str, license_obligations: tuple[str, ...],
    ) -> None:
        job = self.load_job(tenant_id, job_id)
        if job.state is not JobState.ASSET_CANDIDATE:
            raise DurableStoreError("CANDIDATE_STATE_REQUIRED")
        if not _DIGEST.fullmatch(candidate_hash) or not _OPAQUE_REF.fullmatch(quarantine_reference):
            raise DurableStoreError("INVALID_CANDIDATE_REFERENCE")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]+", item) for item in license_obligations):
            raise DurableStoreError("INVALID_LICENSE_OBLIGATION")
        with self._connect() as db:
            obligations = sorted(set(license_obligations))
            manifest_hash = _hash({
                "candidate_hash": candidate_hash, "event_head": job.event_head,
                "job_fingerprint": job.job_fingerprint, "job_id": job.job_id,
                "license_obligations": obligations,
                "quarantine_reference": quarantine_reference,
                "status": "CANDIDATE_NOT_OWNED_ASSET", "tenant_id": tenant_id,
            })
            try:
                db.execute(
                    "INSERT INTO candidate_manifests VALUES(?,?,?,?,?,"
                    "'CANDIDATE_NOT_OWNED_ASSET',?,?)",
                    (tenant_id, job_id, candidate_hash, quarantine_reference,
                     _json(obligations), job.event_head, manifest_hash),
                )
            except sqlite3.IntegrityError:
                raise DurableStoreError("CANDIDATE_ALREADY_EXISTS") from None

    def get_candidate_manifest(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        record = self.load_job(tenant_id, job_id)
        with self._connect() as db:
            self._verify_candidate(db, record)
            row = db.execute(
                "SELECT * FROM candidate_manifests WHERE tenant_id=? AND job_id=?",
                (tenant_id, job_id),
            ).fetchone()
            return dict(row) if row else None

    def get_command_receipt(
        self, tenant_id: str, job_id: str, command_id: str, payload_fingerprint: str,
    ) -> dict[str, Any] | None:
        self.load_job(tenant_id, job_id)
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM command_receipts WHERE tenant_id=? AND job_id=? AND command_id=?",
                (tenant_id, job_id, command_id),
            ).fetchone()
            if row is None:
                return None
            if row["payload_fingerprint"] != payload_fingerprint:
                raise DurableStoreError("IDEMPOTENCY_CONFLICT")
            return dict(row)
