from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from apf.learning_curriculum import CurriculumItem
from apf.learning_evaluator import (
    CandidateLesson,
    EthernianLessonVerification,
    EthernianVerificationService,
    LearningDecision,
    LearningQuestion,
    LessonEvaluation,
    authorize_asset_concept_report,
    evaluate_lesson,
    next_learning_questions,
)
from apf.learning_memory import LearningLesson, LearningMemory


class AccelerationState(StrEnum):
    PLANNED = "PLANNED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    REJECTED = "REJECTED"
    AWAITING_ETHERNIAN_VERIFICATION = "AWAITING_ETHERNIAN_VERIFICATION"
    ETHERNIAN_VERIFIED = "ETHERNIAN_VERIFIED"
    REMEMBERED = "REMEMBERED"
    READY_FOR_HUMAN_AUDIT = "READY_FOR_HUMAN_AUDIT"


@dataclass(frozen=True)
class AccelerationRecord:
    curriculum_item: CurriculumItem
    candidate: CandidateLesson
    lesson: LearningLesson
    evaluation: LessonEvaluation
    state: AccelerationState
    questions: tuple[LearningQuestion, ...] = ()
    verification: EthernianLessonVerification | None = None
    memory_ref: str | None = None
    report_authorization: str | None = None


class LearningAccelerator:
    """Turns curriculum work into verified memory without promoting an asset."""

    def __init__(
        self,
        verification_service: EthernianVerificationService,
        memory: LearningMemory | None = None,
    ) -> None:
        self.memory = memory or LearningMemory()
        self.verification_service = verification_service
        self._records: dict[str, AccelerationRecord] = {}

    def evaluate(
        self,
        item: CurriculumItem,
        candidate: CandidateLesson,
        lesson: LearningLesson,
    ) -> AccelerationRecord:
        if item.candidate_id != candidate.lesson_id:
            raise ValueError("CURRICULUM_CANDIDATE_MISMATCH")
        if lesson.principle.strip() != candidate.principle.strip():
            raise ValueError("LESSON_PRINCIPLE_MISMATCH")

        evaluation = evaluate_lesson(candidate)
        existing = self._records.get(item.candidate_id)
        if existing is not None:
            if (
                existing.evaluation.candidate_fingerprint != evaluation.candidate_fingerprint
                or existing.lesson.content_hash != lesson.content_hash
                or existing.curriculum_item != item
            ):
                raise ValueError("CANDIDATE_ID_CONFLICT")
            return existing

        questions = next_learning_questions(evaluation)
        if evaluation.decision is LearningDecision.REJECT:
            state = AccelerationState.REJECTED
        elif evaluation.decision is LearningDecision.REVISE:
            state = AccelerationState.REVISION_REQUIRED
        else:
            state = AccelerationState.AWAITING_ETHERNIAN_VERIFICATION
        record = AccelerationRecord(item, candidate, lesson, evaluation, state, questions)
        self._records[item.candidate_id] = record
        return record

    def complete_pass(
        self,
        candidate_id: str,
        verification: EthernianLessonVerification,
    ) -> AccelerationRecord:
        record = self._require_record(candidate_id)
        if record.state is AccelerationState.READY_FOR_HUMAN_AUDIT:
            if record.verification == verification:
                return record
            raise ValueError("CANDIDATE_ALREADY_COMPLETED")
        if record.state is not AccelerationState.AWAITING_ETHERNIAN_VERIFICATION:
            raise ValueError(f"INVALID_ACCELERATION_STATE:{record.state}")

        # Authorization performs the fingerprint-bound Ethernian verification.
        authorization = authorize_asset_concept_report(
            record.evaluation,
            verification,
            intent_fingerprint=record.lesson.intent_fingerprint,
            verification_service=self.verification_service,
        )
        verified = replace(record, state=AccelerationState.ETHERNIAN_VERIFIED, verification=verification)
        self._records[candidate_id] = verified

        memory_ref = self.memory.remember(verified.lesson)
        remembered = replace(verified, state=AccelerationState.REMEMBERED, memory_ref=memory_ref)
        self._records[candidate_id] = remembered

        ready = replace(
            remembered,
            state=AccelerationState.READY_FOR_HUMAN_AUDIT,
            report_authorization=authorization,
        )
        self._records[candidate_id] = ready
        return ready

    def get(self, candidate_id: str) -> AccelerationRecord:
        return self._require_record(candidate_id)

    def _require_record(self, candidate_id: str) -> AccelerationRecord:
        try:
            return self._records[candidate_id]
        except KeyError as exc:
            raise ValueError("UNKNOWN_CURRICULUM_CANDIDATE") from exc
