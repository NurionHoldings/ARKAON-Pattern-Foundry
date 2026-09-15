from datetime import UTC, datetime, timedelta

import pytest

from apf.learning_accelerator import AccelerationState, LearningAccelerator
from apf.learning_curriculum import CurriculumItem, LearningMode, LearningOrigin
from apf.learning_evaluator import (
    AssetConceptReportBlocked,
    CandidateLesson,
    EthernianVerificationService,
)
from apf.learning_memory import LearningLesson, LessonOutcome


def item(candidate_id: str = "lesson-1") -> CurriculumItem:
    return CurriculumItem(
        candidate_id=candidate_id,
        origin=LearningOrigin.EXTERNAL,
        mode=LearningMode.EXPLOIT,
        priority=0.9,
        estimated_cost=1,
        reason="GAP_FAILURE_INTENT_PRIORITY",
    )


def candidate(**changes: object) -> CandidateLesson:
    values = {
        "lesson_id": "lesson-1",
        "principle": "Bind approvals to the exact result.",
        "provenance_ref": "evidence://official/spec",
        "intent_alignment": 0.95,
        "counterexample_ref": "test://stale-approval",
        "regression_ref": "test://approval-suite",
        "novelty": 0.7,
        "clean_room_confirmed": True,
    }
    values.update(changes)
    return CandidateLesson(**values)  # type: ignore[arg-type]


def lesson(**changes: object) -> LearningLesson:
    values = {
        "intent_fingerprint": "intent-v1",
        "domain": "governance",
        "problem": "stale approval",
        "failure_mode": None,
        "principle": "Bind approvals to the exact result.",
        "evidence_refs": ("evidence://official/spec", "test://approval-suite"),
        "confidence": 0.95,
        "outcome": LessonOutcome.SUCCESS,
        "verified": True,
    }
    values.update(changes)
    return LearningLesson(**values)  # type: ignore[arg-type]


SECRET = b"accelerator-verification-secret-32-bytes-minimum"
CHECKS = ("PROVENANCE", "INTENT_ALIGNMENT", "COUNTEREXAMPLE", "REGRESSION", "NOVELTY", "CLEAN_ROOM")


def make_accelerator() -> LearningAccelerator:
    return LearningAccelerator(EthernianVerificationService(SECRET))


def verification(instance, record):
    return instance.verification_service.issue(
        record.evaluation,
        intent_fingerprint=record.lesson.intent_fingerprint,
        checks=CHECKS,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def test_pass_is_verified_remembered_and_stops_before_asset_promotion() -> None:
    accelerator = make_accelerator()
    evaluated = accelerator.evaluate(item(), candidate(), lesson())

    assert evaluated.state is AccelerationState.AWAITING_ETHERNIAN_VERIFICATION
    assert len(accelerator.memory) == 0

    ready = accelerator.complete_pass("lesson-1", verification(accelerator, evaluated))

    assert ready.state is AccelerationState.READY_FOR_HUMAN_AUDIT
    assert ready.memory_ref == ready.lesson.content_hash
    assert ready.report_authorization.startswith("ETHERNIAN:lesson-1:")
    assert len(accelerator.memory) == 1
    assert not hasattr(ready, "asset_id")


@pytest.mark.parametrize(
    ("changes", "expected_state"),
    [
        ({"novelty": 0.1}, AccelerationState.REVISION_REQUIRED),
        ({"provenance_ref": ""}, AccelerationState.REJECTED),
    ],
)
def test_revise_and_reject_return_questions_without_entering_memory(changes, expected_state) -> None:
    accelerator = make_accelerator()
    result = accelerator.evaluate(item(), candidate(**changes), lesson())

    assert result.state is expected_state
    assert result.questions
    assert len(accelerator.memory) == 0
    with pytest.raises(ValueError, match="INVALID_ACCELERATION_STATE"):
        accelerator.complete_pass("lesson-1", verification(accelerator, result))


def test_ethernian_verification_must_be_bound_to_exact_candidate() -> None:
    accelerator = make_accelerator()
    record = accelerator.evaluate(item(), candidate(), lesson())

    signed = verification(accelerator, record)
    from dataclasses import replace
    with pytest.raises(AssetConceptReportBlocked, match="CLAIMS_TAMPERED"):
        accelerator.complete_pass("lesson-1", replace(signed, candidate_fingerprint="0" * 64))
    assert accelerator.get("lesson-1").state is AccelerationState.AWAITING_ETHERNIAN_VERIFICATION
    assert len(accelerator.memory) == 0


def test_same_candidate_is_idempotent_but_conflicting_payload_is_rejected() -> None:
    accelerator = make_accelerator()
    first = accelerator.evaluate(item(), candidate(), lesson())
    assert accelerator.evaluate(item(), candidate(), lesson()) is first

    signed = verification(accelerator, first)
    ready = accelerator.complete_pass("lesson-1", signed)
    assert accelerator.complete_pass("lesson-1", signed) is ready
    assert len(accelerator.memory) == 1

    with pytest.raises(ValueError, match="CANDIDATE_ID_CONFLICT"):
        accelerator.evaluate(item(), candidate(novelty=0.8), lesson())


def test_curriculum_identity_and_lesson_principle_are_bound() -> None:
    accelerator = make_accelerator()

    with pytest.raises(ValueError, match="CURRICULUM_CANDIDATE_MISMATCH"):
        accelerator.evaluate(item("different"), candidate(), lesson())
    with pytest.raises(ValueError, match="LESSON_PRINCIPLE_MISMATCH"):
        accelerator.evaluate(item(), candidate(), lesson(principle="Different principle"))
