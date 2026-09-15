from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from apf.learning_safety import LearningSafetyViolation, scan_learning_text


class EvidenceVaultError(ValueError):
    """Base error that never includes evidence content."""


class EvidenceConflictError(EvidenceVaultError):
    """Raised when an existing immutable record is assigned different metadata."""


class EvidenceIntegrityError(EvidenceVaultError):
    """Raised when persisted content no longer matches its evidence identifier."""


class EvidenceNotFoundError(EvidenceVaultError):
    """Raised for a missing or tenant-inaccessible evidence record."""


MetadataValue = str | bool | int | float | None


@dataclass(frozen=True)
class EvidenceMetadata:
    evidence_ref: str
    tenant_id: str
    intent_id: str
    provenance: Mapping[str, MetadataValue]
    license: Mapping[str, MetadataValue]
    byte_length: int
    created_at: datetime


def _canonical_metadata(value: Mapping[str, MetadataValue], field: str) -> str:
    if not isinstance(value, Mapping):
        raise EvidenceVaultError(f"{field.upper()}_INVALID")
    normalized: dict[str, MetadataValue] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, (str, bool, int, float, type(None))):
            raise EvidenceVaultError(f"{field.upper()}_INVALID")
        if isinstance(item, str):
            violations = scan_learning_text(item)
            if violations:
                raise LearningSafetyViolation(violations)
        normalized[key] = item
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class EvidenceVault:
    """Append-only, tenant-scoped evidence storage with content-free normal reads."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence (
                    tenant_id TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    content BLOB NOT NULL,
                    provenance_json TEXT NOT NULL,
                    license_json TEXT NOT NULL,
                    byte_length INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, intent_id, evidence_ref)
                );
                CREATE TRIGGER IF NOT EXISTS evidence_no_update
                BEFORE UPDATE ON evidence BEGIN
                    SELECT RAISE(ABORT, 'EVIDENCE_APPEND_ONLY');
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_no_delete
                BEFORE DELETE ON evidence BEGIN
                    SELECT RAISE(ABORT, 'EVIDENCE_APPEND_ONLY');
                END;
                """
            )

    def store(
        self,
        *,
        tenant_id: str,
        intent_id: str,
        content: str | bytes,
        provenance: Mapping[str, MetadataValue],
        license: Mapping[str, MetadataValue],
    ) -> EvidenceMetadata:
        """Persist safe evidence once and return metadata, never its content."""

        if not tenant_id or not intent_id:
            raise EvidenceVaultError("EVIDENCE_SCOPE_INVALID")
        if isinstance(content, str):
            text = content
            raw = content.encode("utf-8")
        elif isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise EvidenceVaultError("EVIDENCE_CONTENT_NOT_UTF8") from error
            raw = content
        else:
            raise EvidenceVaultError("EVIDENCE_CONTENT_INVALID")
        violations = scan_learning_text(text)
        if violations:
            raise LearningSafetyViolation(violations)

        provenance_json = _canonical_metadata(provenance, "provenance")
        license_json = _canonical_metadata(license, "license")
        evidence_ref = f"evidence://sha256/{hashlib.sha256(raw).hexdigest()}"
        created_at = datetime.now(UTC)

        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM evidence WHERE tenant_id = ? AND intent_id = ? AND evidence_ref = ?",
                (tenant_id, intent_id, evidence_ref),
            ).fetchone()
            if existing is not None:
                if (
                    bytes(existing["content"]) != raw
                    or existing["provenance_json"] != provenance_json
                    or existing["license_json"] != license_json
                ):
                    raise EvidenceConflictError("EVIDENCE_IMMUTABLE_CONFLICT")
                return self._metadata(existing)
            connection.execute(
                """INSERT INTO evidence
                (tenant_id, intent_id, evidence_ref, content, provenance_json,
                 license_json, byte_length, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tenant_id,
                    intent_id,
                    evidence_ref,
                    raw,
                    provenance_json,
                    license_json,
                    len(raw),
                    created_at.isoformat(),
                ),
            )
        return self.get_metadata(tenant_id=tenant_id, intent_id=intent_id, evidence_ref=evidence_ref)

    def get_metadata(self, *, tenant_id: str, intent_id: str, evidence_ref: str) -> EvidenceMetadata:
        """Return scoped metadata. Raw content is deliberately absent from the result."""

        with self._connect() as connection:
            row = connection.execute(
                """SELECT tenant_id, intent_id, evidence_ref, provenance_json,
                license_json, byte_length, created_at FROM evidence
                WHERE tenant_id = ? AND intent_id = ? AND evidence_ref = ?""",
                (tenant_id, intent_id, evidence_ref),
            ).fetchone()
        if row is None:
            raise EvidenceNotFoundError("EVIDENCE_NOT_FOUND")
        return self._metadata(row)

    def verify_integrity(self, *, tenant_id: str, intent_id: str, evidence_ref: str) -> bool:
        """Verify stored bytes against the immutable content-addressed identifier."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT content, byte_length FROM evidence WHERE tenant_id = ? AND intent_id = ? AND evidence_ref = ?",
                (tenant_id, intent_id, evidence_ref),
            ).fetchone()
        if row is None:
            raise EvidenceNotFoundError("EVIDENCE_NOT_FOUND")
        content = bytes(row["content"])
        actual_ref = f"evidence://sha256/{hashlib.sha256(content).hexdigest()}"
        if actual_ref != evidence_ref or len(content) != row["byte_length"]:
            raise EvidenceIntegrityError("EVIDENCE_INTEGRITY_FAILED")
        return True

    @staticmethod
    def _metadata(row: sqlite3.Row) -> EvidenceMetadata:
        return EvidenceMetadata(
            evidence_ref=row["evidence_ref"],
            tenant_id=row["tenant_id"],
            intent_id=row["intent_id"],
            provenance=json.loads(row["provenance_json"]),
            license=json.loads(row["license_json"]),
            byte_length=row["byte_length"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
