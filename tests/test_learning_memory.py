import pytest

from apf.learning_memory import LearningLesson, LearningMemory, LessonOutcome


def lesson(**changes) -> LearningLesson:
    values = {
        "intent_fingerprint": "intent-v1",
        "domain": "collection",
        "problem": "duplicate fetches",
        "failure_mode": None,
        "principle": "Bind deduplication to canonical source identity.",
        "evidence_refs": ("test:test_deduplicates", "audit:run-42"),
        "confidence": 0.95,
        "outcome": LessonOutcome.SUCCESS,
        "verified": True,
    }
    values.update(changes)
    return LearningLesson(**values)


def test_remember_and_recall_are_bound_to_intent_domain_and_problem() -> None:
    memory = LearningMemory()
    expected = lesson()
    memory.remember(expected)
    memory.remember(lesson(problem="redirect escape", principle="Revalidate every redirect."))

    assert memory.recall(
        intent_fingerprint="intent-v1",
        domain="collection",
        problem="duplicate fetches",
    ) == (expected,)
    assert memory.recall(intent_fingerprint="intent-v2", domain="collection") == ()


def test_duplicate_content_hash_is_rejected_even_if_evidence_order_changes() -> None:
    memory = LearningMemory()
    original = lesson()
    memory.remember(original)

    with pytest.raises(ValueError, match="DUPLICATE_LESSON"):
        memory.remember(lesson(evidence_refs=tuple(reversed(original.evidence_refs))))


def test_semantic_duplicate_cannot_bypass_identity_with_verification_metadata() -> None:
    memory = LearningMemory()
    memory.remember(lesson(confidence=0.9, evidence_refs=("test:one",)))

    with pytest.raises(ValueError, match="DUPLICATE_LESSON"):
        memory.remember(
            lesson(
                confidence=1.0,
                evidence_refs=("test:one", "audit:two"),
                domain=" COLLECTION ",
                principle="bind DEDUPLICATION to canonical source identity.",
            )
        )


def test_explicit_upgrade_requires_higher_confidence_and_evidence_superset() -> None:
    memory = LearningMemory()
    original = lesson(confidence=0.9, evidence_refs=("test:one",))
    identity = memory.remember(original)
    stronger = lesson(confidence=0.96, evidence_refs=("test:one", "audit:two"))

    assert memory.upgrade(stronger) == identity
    assert memory.recall(intent_fingerprint="intent-v1", domain="collection") == (stronger,)
    assert len(memory) == 1

    with pytest.raises(ValueError, match="LESSON_UPGRADE_NOT_STRONGER"):
        memory.upgrade(lesson(confidence=0.97, evidence_refs=("audit:different",)))


def test_failure_family_limit_prevents_memory_flood() -> None:
    memory = LearningMemory(failure_family_limit=2)
    common = {
        "failure_mode": "race condition",
        "outcome": LessonOutcome.FAILURE,
    }
    memory.remember(lesson(principle="Acquire a durable lease.", **common))
    memory.remember(lesson(principle="Fence stale lease owners.", **common))

    with pytest.raises(ValueError, match="FAILURE_FAMILY_LIMIT"):
        memory.remember(lesson(principle="Reject expired leases.", **common))
    assert len(memory) == 2


def test_failure_lessons_are_recalled_before_successes() -> None:
    memory = LearningMemory()
    success = lesson(confidence=1.0)
    failure = lesson(
        failure_mode="race condition",
        principle="Use a durable lease before execution.",
        confidence=0.81,
        outcome=LessonOutcome.FAILURE,
    )
    memory.remember(success)
    memory.remember(failure)

    assert memory.recall(intent_fingerprint="intent-v1", domain="collection") == (
        failure,
        success,
    )


@pytest.mark.parametrize(
    ("candidate", "error"),
    [
        (lesson(verified=False), "UNVERIFIED_LESSON"),
        (lesson(confidence=0.79), "LOW_CONFIDENCE_LESSON"),
        (lesson(evidence_refs=()), "EVIDENCE_REQUIRED"),
        (lesson(evidence_refs=("",)), "EVIDENCE_REQUIRED"),
    ],
)
def test_untrusted_lessons_cannot_enter_reusable_memory(candidate, error: str) -> None:
    memory = LearningMemory()

    with pytest.raises(ValueError, match=error):
        memory.remember(candidate)
    assert len(memory) == 0


def test_failure_lesson_requires_named_failure_mode() -> None:
    with pytest.raises(ValueError, match="failure_mode"):
        lesson(outcome=LessonOutcome.FAILURE)


def test_recall_uses_the_same_semantic_normalization_as_storage() -> None:
    memory = LearningMemory()
    original = lesson(confidence=0.9, evidence_refs=("test:one",))
    memory.remember(original)
    stronger = lesson(
        intent_fingerprint=" INTENT-V1 ",
        domain=" COLLECTION ",
        problem="  duplicate   FETCHES ",
        principle="bind DEDUPLICATION to canonical source identity.",
        confidence=0.96,
        evidence_refs=("test:one", "audit:two"),
    )
    memory.upgrade(stronger)

    assert memory.recall(
        intent_fingerprint="intent-v1",
        domain="collection",
        problem="duplicate fetches",
    ) == (stronger,)
