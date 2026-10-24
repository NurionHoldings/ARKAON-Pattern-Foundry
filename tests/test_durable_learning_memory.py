import json
import sqlite3

import pytest

from apf.durable_learning_memory import DurableLearningMemory
from apf.learning_memory import LearningLesson, LearningMemory, LessonOutcome


def lesson(**updates):
    fields = {"intent_fingerprint": "intent-one", "domain": "mailbox", "problem": "missing packet",
              "failure_mode": None, "principle": "Missing transport is not completion.",
              "evidence_refs": ("test:missing-packet",), "confidence": 0.9,
              "outcome": LessonOutcome.SUCCESS, "verified": True}
    return LearningLesson(**{**fields, **updates})


def test_foundry_memory_survives_restart_and_preserves_intent_boundary(tmp_path):
    first = LearningMemory.from_foundry(tmp_path)
    first.remember(lesson())
    second = LearningMemory.from_foundry(tmp_path)
    assert second.recall(intent_fingerprint="intent-one", domain="mailbox") == (lesson(),)
    assert second.recall(intent_fingerprint="other", domain="mailbox") == ()


def test_stale_instances_do_not_lose_lessons_or_accept_duplicates(tmp_path):
    path = tmp_path / "memory.sqlite3"
    first = DurableLearningMemory(path=path)
    second = DurableLearningMemory(path=path)
    first.remember(lesson())
    another = lesson(problem="tampering", principle="Verify digest.")
    second.remember(another)
    assert len(first) == 2
    with pytest.raises(ValueError, match="DUPLICATE_LESSON"):
        second.remember(lesson())
    assert len(DurableLearningMemory(path=path)) == 2


def test_upgrade_persists_and_rejected_upgrade_does_not_replace(tmp_path):
    path = tmp_path / "memory.sqlite3"
    memory = DurableLearningMemory(path=path)
    memory.remember(lesson())
    stronger = lesson(confidence=0.95, evidence_refs=("test:missing-packet", "audit:two"))
    memory.upgrade(stronger)
    with pytest.raises(ValueError, match="NOT_STRONGER"):
        memory.upgrade(lesson())
    assert DurableLearningMemory(path=path).recall(
        intent_fingerprint="intent-one", domain="mailbox") == (stronger,)


def test_corrupt_persisted_lesson_blocks_recall(tmp_path):
    path = tmp_path / "memory.sqlite3"
    memory = DurableLearningMemory(path=path)
    memory.remember(lesson())
    with sqlite3.connect(path) as db:
        payload = json.loads(db.execute("SELECT payload FROM learning_lessons").fetchone()[0])
        payload["principle"] = "tampered"
        db.execute("UPDATE learning_lessons SET payload=?", (json.dumps(payload),))
    with pytest.raises(ValueError, match="LEARNING_STORE_INVALID"):
        memory.recall(intent_fingerprint="intent-one", domain="mailbox")


def test_unverified_lesson_never_persists(tmp_path):
    path = tmp_path / "memory.sqlite3"
    memory = DurableLearningMemory(path=path)
    with pytest.raises(ValueError, match="UNVERIFIED_LESSON"):
        memory.remember(lesson(verified=False))
    assert len(DurableLearningMemory(path=path)) == 0


def test_accelerator_foundry_factory_uses_restart_safe_memory(tmp_path):
    from apf.learning_accelerator import LearningAccelerator
    from apf.learning_evaluator import EthernianVerificationService

    verifier = EthernianVerificationService(b"x" * 32)
    first = LearningAccelerator.from_foundry(foundry_root=tmp_path, verification_service=verifier)
    first.memory.remember(lesson())
    second = LearningAccelerator.from_foundry(foundry_root=tmp_path, verification_service=verifier)
    assert second.memory.recall(intent_fingerprint="intent-one", domain="mailbox") == (lesson(),)
