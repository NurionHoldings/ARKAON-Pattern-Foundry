from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256


class LearningDecision(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    REJECT = "REJECT"


class AssetConceptReportBlocked(ValueError):
    pass


@dataclass(frozen=True)
class CandidateLesson:
    lesson_id: str
    principle: str
    provenance_ref: str
    intent_alignment: float
    counterexample_ref: str
    regression_ref: str
    novelty: float
    clean_room_confirmed: bool


@dataclass(frozen=True)
class LessonEvaluation:
    lesson_id: str
    candidate_fingerprint: str
    decision: LearningDecision
    passed_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]


@dataclass(frozen=True)
class LearningQuestion:
    failed_check: str
    question: str


@dataclass(frozen=True)
class EthernianLessonVerification:
    verifier: str
    candidate_fingerprint: str
    decision: LearningDecision
    checks: tuple[str, ...]


_QUESTIONS = {
    "PROVENANCE": "어떤 권위 있는 원자료와 계보가 이 원칙을 뒷받침하는가?",
    "INTENT_ALIGNMENT": "이 학습이 Intent DNA의 어느 목표와 제약을 충족하는가?",
    "COUNTEREXAMPLE": "이 원칙이 실패하는 반례와 적용 경계는 무엇인가?",
    "REGRESSION": "기존 능력을 훼손하지 않음을 어떤 재현 가능한 시험으로 증명하는가?",
    "NOVELTY": "기존 학습 자산과 구별되는 새로운 효용은 무엇인가?",
    "CLEAN_ROOM": "원본 표현을 복제하지 않은 독립 명세와 구현임을 어떻게 증명하는가?",
}


def candidate_fingerprint(candidate: CandidateLesson) -> str:
    payload = "\x1f".join(
        (
            candidate.lesson_id,
            candidate.principle,
            candidate.provenance_ref,
            str(candidate.intent_alignment),
            candidate.counterexample_ref,
            candidate.regression_ref,
            str(candidate.novelty),
            str(candidate.clean_room_confirmed),
        )
    )
    return sha256(payload.encode()).hexdigest()


def evaluate_lesson(candidate: CandidateLesson) -> LessonEvaluation:
    if not candidate.lesson_id.strip() or not candidate.principle.strip():
        raise ValueError("lesson_id and principle are required")
    if not 0.0 <= candidate.intent_alignment <= 1.0:
        raise ValueError("intent_alignment must be between 0 and 1")
    if not 0.0 <= candidate.novelty <= 1.0:
        raise ValueError("novelty must be between 0 and 1")

    checks = {
        "PROVENANCE": bool(candidate.provenance_ref.strip()),
        "INTENT_ALIGNMENT": candidate.intent_alignment >= 0.8,
        "COUNTEREXAMPLE": bool(candidate.counterexample_ref.strip()),
        "REGRESSION": bool(candidate.regression_ref.strip()),
        "NOVELTY": candidate.novelty >= 0.4,
        "CLEAN_ROOM": candidate.clean_room_confirmed,
    }
    passed = tuple(name for name, result in checks.items() if result)
    failed = tuple(name for name, result in checks.items() if not result)
    if not checks["PROVENANCE"] or not checks["CLEAN_ROOM"]:
        decision = LearningDecision.REJECT
    elif failed:
        decision = LearningDecision.REVISE
    else:
        decision = LearningDecision.PASS
    return LessonEvaluation(
        lesson_id=candidate.lesson_id,
        candidate_fingerprint=candidate_fingerprint(candidate),
        decision=decision,
        passed_checks=passed,
        failed_checks=failed,
    )


def next_learning_questions(evaluation: LessonEvaluation) -> tuple[LearningQuestion, ...]:
    return tuple(LearningQuestion(check, _QUESTIONS[check]) for check in evaluation.failed_checks)


def authorize_asset_concept_report(
    evaluation: LessonEvaluation,
    verification: EthernianLessonVerification | None,
) -> str:
    """Return an authorization reference only after bound Ethernian verification."""
    if evaluation.decision != LearningDecision.PASS:
        raise AssetConceptReportBlocked("LESSON_EVALUATION_NOT_PASSED")
    if verification is None:
        raise AssetConceptReportBlocked("ETHERNIAN_VERIFICATION_REQUIRED")
    if verification.verifier != "ETHERNIAN":
        raise AssetConceptReportBlocked("INVALID_ETHERNIAN_VERIFIER")
    if verification.candidate_fingerprint != evaluation.candidate_fingerprint:
        raise AssetConceptReportBlocked("VERIFICATION_FINGERPRINT_MISMATCH")
    if verification.decision != LearningDecision.PASS or not verification.checks:
        raise AssetConceptReportBlocked("ETHERNIAN_VERIFICATION_FAILED")
    return f"ETHERNIAN:{evaluation.lesson_id}:{evaluation.candidate_fingerprint}"
