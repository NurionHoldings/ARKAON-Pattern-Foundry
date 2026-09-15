from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import floor


class SourceKind(StrEnum):
    OWNED = "OWNED"
    OFFICIAL_STANDARD = "OFFICIAL_STANDARD"
    OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCUMENTATION"
    LICENSED_OPEN_SOURCE = "LICENSED_OPEN_SOURCE"
    CLIENT_DELEGATED = "CLIENT_DELEGATED"


EXTERNAL_KINDS = frozenset(
    {SourceKind.OFFICIAL_STANDARD, SourceKind.OFFICIAL_DOCUMENTATION, SourceKind.LICENSED_OPEN_SOURCE}
)


@dataclass(frozen=True)
class LearningSource:
    source_id: str
    kind: SourceKind
    domain: str
    intent_relevance: float
    authority: float
    license_clarity: float
    recency: float
    novelty: float
    content_hash_seen: bool = False
    derivation_allowed: bool = False

    @property
    def is_external(self) -> bool:
        return self.kind in EXTERNAL_KINDS


@dataclass(frozen=True)
class PlannedSource:
    source_id: str
    score: float
    deep_analysis: bool
    reason: str


def score_source(source: LearningSource) -> float:
    """Rank evidence quality without treating popularity as authority."""
    score = (
        source.intent_relevance * 0.35
        + source.authority * 0.25
        + source.license_clarity * 0.15
        + source.novelty * 0.15
        + source.recency * 0.10
    )
    if source.is_external:
        score += 0.05
    return min(round(score, 6), 1.0)


def plan_learning(
    sources: list[LearningSource],
    *,
    max_sources: int,
    external_target_ratio: float = 0.65,
) -> list[PlannedSource]:
    """Select a bounded, evidence-diverse learning set with external-first capacity."""
    if max_sources < 1:
        return []
    eligible = [s for s in sources if s.intent_relevance >= 0.30 and not s.content_hash_seen]
    ranked = sorted(eligible, key=lambda s: (-score_source(s), s.source_id))
    ratio = min(max(external_target_ratio, 0.0), 1.0)
    external_slots = floor(max_sources * ratio)
    internal_slots = max_sources - external_slots
    external = [s for s in ranked if s.is_external]
    internal = [s for s in ranked if not s.is_external]

    # Reserve both sides of the governed budget before filling unused capacity.
    # This prevents high-scoring external evidence from silently erasing the
    # internal operational baseline when both pools are available.
    selected: list[LearningSource] = []
    selected.extend(external[:external_slots])
    selected.extend(internal[:internal_slots])
    selected_ids = {s.source_id for s in selected}
    selected.extend([s for s in ranked if s.source_id not in selected_ids][: max_sources - len(selected)])
    return [
        PlannedSource(
            source_id=s.source_id,
            score=score_source(s),
            deep_analysis=True,
            reason="EXTERNAL_PRIORITY" if s.is_external else "INTENT_RELEVANT_INTERNAL_BASELINE",
        )
        for s in selected
    ]


def may_create_reusable_derivative(source: LearningSource) -> bool:
    return source.derivation_allowed and source.license_clarity >= 0.8

