from __future__ import annotations

import base64
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from threading import Lock
from uuid import UUID, uuid4


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
    intent_fingerprint: str
    evaluation_digest: str
    decision: LearningDecision
    checks: tuple[str, ...]
    expires_at: datetime
    nonce: UUID
    token: str


_REQUIRED_VERIFICATION_CHECKS = frozenset(
    {"PROVENANCE", "INTENT_ALIGNMENT", "COUNTEREXAMPLE", "REGRESSION", "NOVELTY", "CLEAN_ROOM"}
)


def evaluation_digest(evaluation: LessonEvaluation) -> str:
    payload = json.dumps(
        {
            "candidate_fingerprint": evaluation.candidate_fingerprint,
            "decision": evaluation.decision,
            "failed_checks": evaluation.failed_checks,
            "lesson_id": evaluation.lesson_id,
            "passed_checks": evaluation.passed_checks,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode()).hexdigest()


class EthernianVerificationService:
    """Issues and atomically consumes signed, narrowly-bound lesson verification."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("VERIFICATION_SECRET_TOO_SHORT")
        self._secret = secret
        self._consumed: set[UUID] = set()
        self._lock = Lock()

    def issue(
        self,
        evaluation: LessonEvaluation,
        *,
        intent_fingerprint: str,
        checks: tuple[str, ...],
        expires_at: datetime,
    ) -> EthernianLessonVerification:
        if not intent_fingerprint.strip():
            raise AssetConceptReportBlocked("INTENT_FINGERPRINT_REQUIRED")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise AssetConceptReportBlocked("TIMEZONE_AWARE_EXPIRY_REQUIRED")
        if set(checks) != _REQUIRED_VERIFICATION_CHECKS or len(checks) != len(set(checks)):
            raise AssetConceptReportBlocked("INCOMPLETE_ETHERNIAN_CHECKS")
        nonce = uuid4()
        digest = evaluation_digest(evaluation)
        normalized_expiry = datetime.fromtimestamp(
            int(expires_at.astimezone(UTC).timestamp()), UTC
        )
        payload = {
            "candidate_fingerprint": evaluation.candidate_fingerprint,
            "checks": sorted(checks),
            "decision": LearningDecision.PASS,
            "evaluation_digest": digest,
            "expires_at": int(normalized_expiry.timestamp()),
            "intent_fingerprint": intent_fingerprint,
            "nonce": str(nonce),
            "verifier": "ETHERNIAN",
            "version": 1,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).rstrip(b"=").decode("ascii")
        signature = base64.urlsafe_b64encode(
            hmac.digest(self._secret, encoded.encode("ascii"), "sha256")
        ).rstrip(b"=").decode("ascii")
        return EthernianLessonVerification(
            verifier="ETHERNIAN",
            candidate_fingerprint=evaluation.candidate_fingerprint,
            intent_fingerprint=intent_fingerprint,
            evaluation_digest=digest,
            decision=LearningDecision.PASS,
            checks=checks,
            expires_at=normalized_expiry,
            nonce=nonce,
            token=f"{encoded}.{signature}",
        )

    def verify_and_consume(
        self,
        evaluation: LessonEvaluation,
        verification: EthernianLessonVerification,
        *,
        intent_fingerprint: str,
        now: datetime | None = None,
    ) -> None:
        try:
            encoded, supplied = verification.token.split(".")
            expected = base64.urlsafe_b64encode(
                hmac.digest(self._secret, encoded.encode("ascii"), "sha256")
            ).rstrip(b"=").decode("ascii")
            if not hmac.compare_digest(supplied, expected):
                raise ValueError
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            payload = json.loads(raw)
            if payload["version"] != 1:
                raise ValueError
            nonce = UUID(payload["nonce"])
            expires_at = datetime.fromtimestamp(payload["expires_at"], UTC)
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise AssetConceptReportBlocked("INVALID_ETHERNIAN_SIGNATURE") from exc

        signed = (
            payload["verifier"], payload["candidate_fingerprint"], payload["intent_fingerprint"],
            payload["evaluation_digest"], payload["decision"], tuple(payload["checks"]), expires_at, nonce,
        )
        presented = (
            verification.verifier, verification.candidate_fingerprint, verification.intent_fingerprint,
            verification.evaluation_digest, verification.decision, tuple(sorted(verification.checks)),
            verification.expires_at.astimezone(UTC), verification.nonce,
        )
        if signed != presented:
            raise AssetConceptReportBlocked("VERIFICATION_CLAIMS_TAMPERED")
        if (
            verification.verifier != "ETHERNIAN"
            or verification.candidate_fingerprint != evaluation.candidate_fingerprint
            or verification.intent_fingerprint != intent_fingerprint
            or verification.evaluation_digest != evaluation_digest(evaluation)
        ):
            raise AssetConceptReportBlocked("VERIFICATION_BINDING_MISMATCH")
        if set(verification.checks) != _REQUIRED_VERIFICATION_CHECKS:
            raise AssetConceptReportBlocked("INCOMPLETE_ETHERNIAN_CHECKS")
        checked_at = now or datetime.now(UTC)
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise AssetConceptReportBlocked("TIMEZONE_AWARE_VERIFICATION_REQUIRED")
        if checked_at.astimezone(UTC) >= expires_at:
            raise AssetConceptReportBlocked("ETHERNIAN_VERIFICATION_EXPIRED")
        with self._lock:
            if nonce in self._consumed:
                raise AssetConceptReportBlocked("ETHERNIAN_VERIFICATION_ALREADY_USED")
            self._consumed.add(nonce)


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
    *,
    intent_fingerprint: str,
    verification_service: EthernianVerificationService,
    now: datetime | None = None,
) -> str:
    """Return an authorization reference only after bound Ethernian verification."""
    if evaluation.decision != LearningDecision.PASS:
        raise AssetConceptReportBlocked("LESSON_EVALUATION_NOT_PASSED")
    if verification is None:
        raise AssetConceptReportBlocked("ETHERNIAN_VERIFICATION_REQUIRED")
    if verification.decision != LearningDecision.PASS:
        raise AssetConceptReportBlocked("ETHERNIAN_VERIFICATION_FAILED")
    verification_service.verify_and_consume(
        evaluation, verification, intent_fingerprint=intent_fingerprint, now=now
    )
    return f"ETHERNIAN:{evaluation.lesson_id}:{evaluation.candidate_fingerprint}"
