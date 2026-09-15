from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

MIN_REUSABLE_CONFIDENCE = 0.8
DEFAULT_FAILURE_FAMILY_LIMIT = 3


def _normalize_semantic_text(value: str | None) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


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

    @property
    def semantic_identity_hash(self) -> str:
        """Stable identity that excludes mutable verification strength."""
        payload = {
            "domain": _normalize_semantic_text(self.domain),
            "failure_mode": _normalize_semantic_text(self.failure_mode),
            "intent_fingerprint": _normalize_semantic_text(self.intent_fingerprint),
            "outcome": self.outcome.value,
            "principle": _normalize_semantic_text(self.principle),
            "problem": _normalize_semantic_text(self.problem),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def failure_family_hash(self) -> str:
        payload = {
            "domain": _normalize_semantic_text(self.domain),
            "failure_mode": _normalize_semantic_text(self.failure_mode),
            "intent_fingerprint": _normalize_semantic_text(self.intent_fingerprint),
            "problem": _normalize_semantic_text(self.problem),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class LearningMemory:
    """Stores reusable, evidence-backed lessons for ARKAON workers."""

    def __init__(
        self,
        *,
        minimum_confidence: float = MIN_REUSABLE_CONFIDENCE,
        failure_family_limit: int = DEFAULT_FAILURE_FAMILY_LIMIT,
    ) -> None:
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if failure_family_limit < 1:
            raise ValueError("failure_family_limit must be positive")
        self.minimum_confidence = minimum_confidence
        self.failure_family_limit = failure_family_limit
        self._lessons: dict[str, LearningLesson] = {}

    def remember(self, lesson: LearningLesson) -> str:
        self._validate_reusable(lesson)
        digest = lesson.semantic_identity_hash
        if digest in self._lessons:
            raise ValueError("DUPLICATE_LESSON")
        self._validate_failure_family_capacity(lesson)
        self._lessons[digest] = lesson
        return digest

    def upgrade(self, lesson: LearningLesson) -> str:
        """Replace the same semantic lesson only with strictly stronger evidence."""
        self._validate_reusable(lesson)
        digest = lesson.semantic_identity_hash
        existing = self._lessons.get(digest)
        if existing is None:
            raise ValueError("LESSON_NOT_FOUND")

        old_evidence = {_normalize_semantic_text(ref) for ref in existing.evidence_refs}
        new_evidence = {_normalize_semantic_text(ref) for ref in lesson.evidence_refs}
        if lesson.confidence <= existing.confidence or not new_evidence > old_evidence:
            raise ValueError("LESSON_UPGRADE_NOT_STRONGER")

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
        normalized_intent = _normalize_semantic_text(intent_fingerprint)
        normalized_domain = _normalize_semantic_text(domain)
        normalized_problem = None if problem is None else _normalize_semantic_text(problem)
        matches = [
            lesson
            for lesson in self._lessons.values()
            if _normalize_semantic_text(lesson.intent_fingerprint) == normalized_intent
            and _normalize_semantic_text(lesson.domain) == normalized_domain
            and (
                normalized_problem is None
                or _normalize_semantic_text(lesson.problem) == normalized_problem
            )
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

    def _validate_failure_family_capacity(self, lesson: LearningLesson) -> None:
        if lesson.outcome is not LessonOutcome.FAILURE:
            return
        family_size = sum(
            existing.outcome is LessonOutcome.FAILURE
            and existing.failure_family_hash == lesson.failure_family_hash
            for existing in self._lessons.values()
        )
        if family_size >= self.failure_family_limit:
            raise ValueError("FAILURE_FAMILY_LIMIT")
