from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import UUID

from apf.development_orchestrator import (
    DevelopmentOrchestrator,
    TaskContract,
    TaskKind,
    TaskStatus,
)


class OrchestratorStorageError(RuntimeError):
    """Raised when persisted task state cannot be trusted or decoded."""


class SQLiteOrchestratorStorage:
    """Durable, authenticated storage for ARKAON task contracts.

    Payloads are canonical JSON authenticated with an application-provided HMAC key.
    This detects both accidental corruption and database-only tampering before a task
    is restored into the orchestrator.
    """

    def __init__(self, database_path: str | Path, *, integrity_key: bytes) -> None:
        if len(integrity_key) < 32:
            raise ValueError("INTEGRITY_KEY_MUST_BE_AT_LEAST_32_BYTES")
        self._database_path = Path(database_path)
        self._integrity_key = integrity_key
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_tasks (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    integrity_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save(self, contract: TaskContract) -> None:
        self.save_many((contract,))

    def save_many(self, contracts: Iterable[TaskContract]) -> None:
        rows = []
        for contract in contracts:
            payload = serialize_task_contract(contract)
            rows.append((str(contract.task_id), payload, self._sign(payload)))
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO orchestrator_tasks (task_id, payload, integrity_hash)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    payload = excluded.payload,
                    integrity_hash = excluded.integrity_hash,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )

    def load(self, task_id: UUID) -> TaskContract | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT task_id, payload, integrity_hash FROM orchestrator_tasks WHERE task_id = ?",
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return self._decode_row(*row)

    def load_all(self) -> tuple[TaskContract, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_id, payload, integrity_hash
                FROM orchestrator_tasks
                ORDER BY task_id
                """
            ).fetchall()
        return tuple(self._decode_row(*row) for row in rows)

    def restore_into(self, orchestrator: DevelopmentOrchestrator) -> int:
        contracts = self.load_all()
        for contract in contracts:
            restored = orchestrator.submit(contract)
            if restored != contract:
                raise OrchestratorStorageError("RESTORED_TASK_STATE_CHANGED")
        return len(contracts)

    def _sign(self, payload: str) -> str:
        return hmac.new(self._integrity_key, payload.encode(), hashlib.sha256).hexdigest()

    def _decode_row(self, task_id: str, payload: str, integrity_hash: str) -> TaskContract:
        if not hmac.compare_digest(self._sign(payload), integrity_hash):
            raise OrchestratorStorageError(f"TASK_INTEGRITY_CHECK_FAILED:{task_id}")
        try:
            contract = deserialize_task_contract(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OrchestratorStorageError(f"INVALID_TASK_PAYLOAD:{task_id}") from exc
        if str(contract.task_id) != task_id:
            raise OrchestratorStorageError(f"TASK_ID_MISMATCH:{task_id}")
        return contract


def serialize_task_contract(contract: TaskContract) -> str:
    payload: dict[str, Any] = {
        "allowed_paths": list(contract.allowed_paths),
        "approval_ref": contract.approval_ref,
        "claimed_by": contract.claimed_by,
        "dependencies": [str(dependency) for dependency in contract.dependencies],
        "expected_artifacts": list(contract.expected_artifacts),
        "intent_fingerprint": contract.intent_fingerprint,
        "kind": contract.kind.value,
        "lease_token": str(contract.lease_token) if contract.lease_token else None,
        "objective": contract.objective,
        "produced_artifacts": list(contract.produced_artifacts),
        "requested_operations": list(contract.requested_operations),
        "status": contract.status.value,
        "task_id": str(contract.task_id),
        "version": 2,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def deserialize_task_contract(payload: str) -> TaskContract:
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get("version") not in (1, 2):
        raise ValueError("UNSUPPORTED_TASK_PAYLOAD_VERSION")
    required = {
        "allowed_paths",
        "approval_ref",
        "dependencies",
        "expected_artifacts",
        "intent_fingerprint",
        "kind",
        "lease_token",
        "objective",
        "produced_artifacts",
        "requested_operations",
        "status",
        "task_id",
        "version",
    }
    if data["version"] == 2:
        required.add("claimed_by")
    if set(data) != required:
        raise ValueError("INVALID_TASK_PAYLOAD_FIELDS")
    return TaskContract(
        task_id=UUID(data["task_id"]),
        kind=TaskKind(data["kind"]),
        intent_fingerprint=_string(data["intent_fingerprint"]),
        objective=_string(data["objective"]),
        allowed_paths=_string_tuple(data["allowed_paths"]),
        expected_artifacts=_string_tuple(data["expected_artifacts"]),
        dependencies=tuple(UUID(value) for value in data["dependencies"]),
        requested_operations=_string_tuple(data["requested_operations"]),
        approval_ref=None if data["approval_ref"] is None else _string(data["approval_ref"]),
        status=TaskStatus(data["status"]),
        lease_token=None if data["lease_token"] is None else UUID(data["lease_token"]),
        claimed_by=(
            None
            if data.get("claimed_by") is None
            else _string(data["claimed_by"])
        ),
        produced_artifacts=_string_tuple(data["produced_artifacts"]),
    )


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("EXPECTED_STRING")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("EXPECTED_STRING_LIST")
    return tuple(value)
