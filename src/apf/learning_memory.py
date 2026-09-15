from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

MIN_REUSABLE_CONFIDENCE = 0.8


class LessonOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


@dataclass(frozen=True)
class LearningLesson:
    intent_fingerprint: str
    domain: str
    problem: str
    failure_mode: str | None
    principle: str
    evidence_refs: tuple[str, ...]
    confidence: float
    outcome: LessonOutcome
    verified: bool

    def __post_init__(self) -> None:
        required = {
            "intent_fingerprint": self.intent_fingerprint,
            "domain": self.domain,
            "problem": self.problem,
            "principle": self.principle,
        }
        if any(not value.strip() for value in required.values()):
            raise ValueError("lesson identity and principle fields must not be blank")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.outcome is LessonOutcome.FAILURE and not (self.failure_mode or "").strip():
            raise ValueError("failure lessons require a failure_mode")

    @property
    def content_hash(self) -> str:
        payload = {
            "confidence": self.confidence,
            "domain": self.domain.strip(),
            "evidence_refs": sorted(ref.strip() for ref in self.evidence_refs),
            "failure_mode": (self.failure_mode or "").strip(),
            "intent_fingerprint": self.intent_fingerprint.strip(),
            "outcome": self.outcome.value,
            "principle": self.principle.strip(),
            "problem": self.problem.strip(),
            "verified": self.verified,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class LearningMemory:
    """Stores reusable, evidence-backed lessons for ARKAON workers."""

    def __init__(self, *, minimum_confidence: float = MIN_REUSABLE_CONFIDENCE) -> None:
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self.minimum_confidence = minimum_confidence
        self._lessons: dict[str, LearningLesson] = {}

    def remember(self, lesson: LearningLesson) -> str:
        self._validate_reusable(lesson)
        digest = lesson.content_hash
        if digest in self._lessons:
            raise ValueError("DUPLICATE_LESSON")
        self._lessons[digest] = lesson
        return digest

    def recall(
        self,
        *,
        intent_fingerprint: str,
        domain: str,
        problem: str | None = None,
        limit: int = 10,
    ) -> tuple[LearningLesson, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        matches = [
            lesson
            for lesson in self._lessons.values()
            if lesson.intent_fingerprint == intent_fingerprint
            and lesson.domain == domain
            and (problem is None or lesson.problem == problem)
            and self._is_reusable(lesson)
        ]
        matches.sort(
            key=lambda lesson: (
                lesson.outcome is not LessonOutcome.FAILURE,
                -lesson.confidence,
                lesson.content_hash,
            )
        )
        return tuple(matches[:limit])

    def __len__(self) -> int:
        return len(self._lessons)

    def _validate_reusable(self, lesson: LearningLesson) -> None:
        if not lesson.verified:
            raise ValueError("UNVERIFIED_LESSON")
        if lesson.confidence < self.minimum_confidence:
            raise ValueError("LOW_CONFIDENCE_LESSON")
        if not lesson.evidence_refs or any(not ref.strip() for ref in lesson.evidence_refs):
            raise ValueError("EVIDENCE_REQUIRED")

    def _is_reusable(self, lesson: LearningLesson) -> bool:
        return (
            lesson.verified
            and lesson.confidence >= self.minimum_confidence
            and bool(lesson.evidence_refs)
            and all(ref.strip() for ref in lesson.evidence_refs)
        )
