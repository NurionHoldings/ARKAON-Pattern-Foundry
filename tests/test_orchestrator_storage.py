from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from apf.development_orchestrator import (
    DevelopmentOrchestrator,
    TaskKind,
    TaskStatus,
    Worker,
    task_contract,
)
from apf.orchestrator_storage import (
    OrchestratorStorageError,
    SQLiteOrchestratorStorage,
    deserialize_task_contract,
    serialize_task_contract,
)

INTEGRITY_KEY = b"arkaon-test-integrity-key-32-bytes-minimum"


def contract():
    return task_contract(
        TaskKind.BUILD,
        intent_fingerprint="intent:abc123",
        objective="영속 작업 큐 구현",
        allowed_paths=("src/apf", "tests"),
        expected_artifacts=("implementation.patch",),
        dependencies=(uuid4(),),
        requested_operations=("WRITE_SCOPED_FILES",),
        approval_ref="approval:7",
    )


def test_task_contract_canonical_round_trip() -> None:
    original = replace(
        contract(),
        status=TaskStatus.RUNNING,
        lease_token=uuid4(),
        produced_artifacts=("partial.patch",),
    )

    encoded = serialize_task_contract(original)

    assert deserialize_task_contract(encoded) == original
    assert serialize_task_contract(deserialize_task_contract(encoded)) == encoded


def test_storage_survives_reopen_and_restores_exact_state(tmp_path) -> None:
    path = tmp_path / "orchestrator.sqlite3"
    original = replace(contract(), status=TaskStatus.RUNNING, lease_token=uuid4())
    SQLiteOrchestratorStorage(path, integrity_key=INTEGRITY_KEY).save(original)

    reopened = SQLiteOrchestratorStorage(path, integrity_key=INTEGRITY_KEY)
    assert reopened.load(original.task_id) == original
    assert reopened.load(uuid4()) is None

    orchestrator = DevelopmentOrchestrator()
    assert reopened.restore_into(orchestrator) == 1
    assert orchestrator.get(original.task_id) == original


def test_save_many_is_atomic_and_load_all_is_deterministic(tmp_path) -> None:
    storage = SQLiteOrchestratorStorage(tmp_path / "queue.db", integrity_key=INTEGRITY_KEY)
    first = contract()
    second = replace(contract(), task_id=uuid4(), kind=TaskKind.TEST)

    storage.save_many((second, first))

    loaded = storage.load_all()
    assert {task.task_id for task in loaded} == {first.task_id, second.task_id}
    assert [str(task.task_id) for task in loaded] == sorted(str(task.task_id) for task in loaded)


def test_storage_rejects_payload_tampering(tmp_path) -> None:
    path = tmp_path / "queue.db"
    original = contract()
    storage = SQLiteOrchestratorStorage(path, integrity_key=INTEGRITY_KEY)
    storage.save(original)
    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM orchestrator_tasks WHERE task_id = ?",
                (str(original.task_id),),
            ).fetchone()[0]
        )
        payload["objective"] = "tampered objective"
        connection.execute(
            "UPDATE orchestrator_tasks SET payload = ? WHERE task_id = ?",
            (json.dumps(payload), str(original.task_id)),
        )

    with pytest.raises(OrchestratorStorageError, match="TASK_INTEGRITY_CHECK_FAILED"):
        storage.load(original.task_id)


def test_storage_rejects_wrong_integrity_key(tmp_path) -> None:
    path = tmp_path / "queue.db"
    original = contract()
    SQLiteOrchestratorStorage(path, integrity_key=INTEGRITY_KEY).save(original)
    wrong_key_storage = SQLiteOrchestratorStorage(path, integrity_key=b"x" * 32)

    with pytest.raises(OrchestratorStorageError, match="TASK_INTEGRITY_CHECK_FAILED"):
        wrong_key_storage.load(original.task_id)


def test_claimed_task_can_be_saved_and_resumed_after_restart(tmp_path) -> None:
    original_orchestrator = DevelopmentOrchestrator()
    queued = replace(contract(), dependencies=())
    original_orchestrator.submit(queued)
    claimed = original_orchestrator.claim(Worker("builder-1", frozenset({TaskKind.BUILD})))
    assert claimed is not None

    path = tmp_path / "queue.db"
    SQLiteOrchestratorStorage(path, integrity_key=INTEGRITY_KEY).save(claimed)
    restarted = DevelopmentOrchestrator()
    SQLiteOrchestratorStorage(path, integrity_key=INTEGRITY_KEY).restore_into(restarted)

    assert restarted.get(claimed.task_id) == claimed


def test_short_integrity_key_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="INTEGRITY_KEY_MUST_BE_AT_LEAST_32_BYTES"):
        SQLiteOrchestratorStorage(tmp_path / "queue.db", integrity_key=b"short")
