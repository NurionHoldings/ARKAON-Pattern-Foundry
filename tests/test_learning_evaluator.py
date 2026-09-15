import pytest

from apf.learning_evaluator import (
    AssetConceptReportBlocked,
    CandidateLesson,
    EthernianLessonVerification,
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


def verification(evaluation, **changes: object) -> EthernianLessonVerification:
    values = {
        "verifier": "ETHERNIAN",
        "candidate_fingerprint": evaluation.candidate_fingerprint,
        "decision": LearningDecision.PASS,
        "checks": ("PROVENANCE", "INTENT", "CLEAN_ROOM", "REGRESSION"),
    }
    values.update(changes)
    return EthernianLessonVerification(**values)  # type: ignore[arg-type]


def test_complete_candidate_passes_and_can_be_reported_after_ethernian_verification():
    result = evaluate_lesson(candidate())

    assert result.decision == LearningDecision.PASS
    assert result.failed_checks == ()
    assert authorize_asset_concept_report(result, verification(result)).startswith("ETHERNIAN:lesson-1:")


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

    with pytest.raises(AssetConceptReportBlocked, match="ETHERNIAN_VERIFICATION_REQUIRED"):
        authorize_asset_concept_report(result, None)


def test_report_rejects_verification_bound_to_different_candidate():
    result = evaluate_lesson(candidate())

    with pytest.raises(AssetConceptReportBlocked, match="FINGERPRINT_MISMATCH"):
        authorize_asset_concept_report(
            result,
            verification(result, candidate_fingerprint="0" * 64),
        )


def test_failed_lesson_cannot_be_reported_even_with_verification():
    result = evaluate_lesson(candidate(novelty=0.1))

    with pytest.raises(AssetConceptReportBlocked, match="LESSON_EVALUATION_NOT_PASSED"):
        authorize_asset_concept_report(result, verification(result))


@pytest.mark.parametrize("field,value", [("intent_alignment", 1.1), ("novelty", -0.1)])
def test_scores_must_be_normalized(field, value):
    with pytest.raises(ValueError, match="between 0 and 1"):
        evaluate_lesson(candidate(**{field: value}))
