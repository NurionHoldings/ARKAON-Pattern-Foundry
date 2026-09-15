from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from apf.learning_evaluator import (
    AssetConceptReportBlocked,
    CandidateLesson,
    EthernianVerificationService,
    LearningDecision,
    authorize_asset_concept_report,
    evaluate_lesson,
    next_learning_questions,
)


def candidate(**changes: object) -> CandidateLesson:
    values = {
        "lesson_id": "lesson-1",
        "principle": "Bind approvals to the exact proposed result.",
        "provenance_ref": "evidence://official/spec",
        "intent_alignment": 0.95,
        "counterexample_ref": "test://stale-approval",
        "regression_ref": "test://approval-suite",
        "novelty": 0.7,
        "clean_room_confirmed": True,
    }
    values.update(changes)
    return CandidateLesson(**values)  # type: ignore[arg-type]


SECRET = b"evaluator-verification-secret-32-bytes-minimum"
CHECKS = ("PROVENANCE", "INTENT_ALIGNMENT", "COUNTEREXAMPLE", "REGRESSION", "NOVELTY", "CLEAN_ROOM")


def verification(service, evaluation):
    return service.issue(
        evaluation,
        intent_fingerprint="intent-v1",
        checks=CHECKS,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def test_complete_candidate_passes_and_can_be_reported_after_ethernian_verification():
    result = evaluate_lesson(candidate())
    service = EthernianVerificationService(SECRET)

    assert result.decision == LearningDecision.PASS
    assert result.failed_checks == ()
    assert authorize_asset_concept_report(
        result, verification(service, result), intent_fingerprint="intent-v1", verification_service=service
    ).startswith("ETHERNIAN:lesson-1:")


@pytest.mark.parametrize("field", ["provenance_ref", "clean_room_confirmed"])
def test_provenance_or_clean_room_failure_rejects_learning(field):
    result = evaluate_lesson(candidate(**{field: "" if field == "provenance_ref" else False}))

    assert result.decision == LearningDecision.REJECT
    assert ("PROVENANCE" if field == "provenance_ref" else "CLEAN_ROOM") in result.failed_checks


def test_recoverable_failures_become_next_learning_questions():
    result = evaluate_lesson(
        candidate(intent_alignment=0.6, counterexample_ref="", regression_ref="", novelty=0.2)
    )

    assert result.decision == LearningDecision.REVISE
    questions = next_learning_questions(result)
    assert tuple(item.failed_check for item in questions) == (
        "INTENT_ALIGNMENT",
        "COUNTEREXAMPLE",
        "REGRESSION",
        "NOVELTY",
    )
    assert all(item.question.endswith("?") for item in questions)


def test_report_is_blocked_before_ethernian_verification():
    result = evaluate_lesson(candidate())
    service = EthernianVerificationService(SECRET)

    with pytest.raises(AssetConceptReportBlocked, match="ETHERNIAN_VERIFICATION_REQUIRED"):
        authorize_asset_concept_report(
            result, None, intent_fingerprint="intent-v1", verification_service=service
        )


def test_report_rejects_verification_bound_to_different_candidate():
    result = evaluate_lesson(candidate())
    service = EthernianVerificationService(SECRET)
    signed = verification(service, result)

    with pytest.raises(AssetConceptReportBlocked, match="CLAIMS_TAMPERED"):
        authorize_asset_concept_report(
            result,
            replace(signed, candidate_fingerprint="0" * 64),
            intent_fingerprint="intent-v1",
            verification_service=service,
        )


def test_failed_lesson_cannot_be_reported_even_with_verification():
    result = evaluate_lesson(candidate(novelty=0.1))
    service = EthernianVerificationService(SECRET)

    with pytest.raises(AssetConceptReportBlocked, match="LESSON_EVALUATION_NOT_PASSED"):
        authorize_asset_concept_report(
            result, verification(service, result), intent_fingerprint="intent-v1", verification_service=service
        )


def test_verification_blocks_reuse_expiry_and_incomplete_checks():
    result = evaluate_lesson(candidate())
    service = EthernianVerificationService(SECRET)
    signed = verification(service, result)
    authorize_asset_concept_report(
        result, signed, intent_fingerprint="intent-v1", verification_service=service
    )
    with pytest.raises(AssetConceptReportBlocked, match="ALREADY_USED"):
        authorize_asset_concept_report(
            result, signed, intent_fingerprint="intent-v1", verification_service=service
        )

    expired = service.issue(
        result,
        intent_fingerprint="intent-v1",
        checks=CHECKS,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(AssetConceptReportBlocked, match="EXPIRED"):
        authorize_asset_concept_report(
            result, expired, intent_fingerprint="intent-v1", verification_service=service
        )
    with pytest.raises(AssetConceptReportBlocked, match="INCOMPLETE"):
        service.issue(
            result,
            intent_fingerprint="intent-v1",
            checks=CHECKS[:-1],
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )


@pytest.mark.parametrize("field,value", [("intent_alignment", 1.1), ("novelty", -0.1)])
def test_scores_must_be_normalized(field, value):
    with pytest.raises(ValueError, match="between 0 and 1"):
        evaluate_lesson(candidate(**{field: value}))
