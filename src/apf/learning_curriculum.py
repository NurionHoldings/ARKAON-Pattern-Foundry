from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import floor


class LearningOrigin(StrEnum):
    EXTERNAL = "EXTERNAL"
    INTERNAL = "INTERNAL"


class LearningMode(StrEnum):
    EXPLOIT = "EXPLOIT"
    EXPLORE = "EXPLORE"


@dataclass(frozen=True)
class LearningCandidate:
    candidate_id: str
    origin: LearningOrigin
    knowledge_gap: float
    failure_frequency: float
    intent_relevance: float
    novelty: float
    estimated_cost: int = 1
    content_fingerprint: str | None = None
    already_learned: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        if self.estimated_cost < 1:
            raise ValueError("estimated_cost must be positive")
        for name in ("knowledge_gap", "failure_frequency", "intent_relevance", "novelty"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class CurriculumItem:
    candidate_id: str
    origin: LearningOrigin
    mode: LearningMode
    priority: float
    estimated_cost: int
    reason: str


@dataclass(frozen=True)
class CurriculumPlan:
    items: tuple[CurriculumItem, ...]
    budget_limit: int
    budget_spent: int
    external_slots: int
    internal_slots: int
    rejected_ids: tuple[str, ...]


def active_learning_priority(candidate: LearningCandidate) -> float:
    """Score work that closes gaps and recurring failures while preserving intent."""
    return round(
        candidate.knowledge_gap * 0.35
        + candidate.failure_frequency * 0.25
        + candidate.intent_relevance * 0.25
        + candidate.novelty * 0.15,
        6,
    )


def _deduplicate(
    candidates: list[LearningCandidate], min_intent_relevance: float
) -> tuple[list[LearningCandidate], set[str]]:
    rejected = {
        candidate.candidate_id
        for candidate in candidates
        if candidate.already_learned or candidate.intent_relevance < min_intent_relevance
    }
    eligible = [candidate for candidate in candidates if candidate.candidate_id not in rejected]
    grouped: dict[str, list[LearningCandidate]] = {}
    for candidate in eligible:
        key = candidate.content_fingerprint or f"candidate:{candidate.candidate_id}"
        grouped.setdefault(key, []).append(candidate)

    unique: list[LearningCandidate] = []
    for group in grouped.values():
        ranked = sorted(group, key=lambda item: (-active_learning_priority(item), item.candidate_id))
        unique.append(ranked[0])
        rejected.update(item.candidate_id for item in ranked[1:])
    return unique, rejected


def _select_pool(
    candidates: list[LearningCandidate],
    *,
    slots: int,
    budget: int,
    exploration_ratio: float,
) -> tuple[list[tuple[LearningCandidate, LearningMode]], int]:
    if slots < 1 or budget < 1:
        return [], 0
    exploit_ranked = sorted(
        candidates,
        key=lambda item: (-active_learning_priority(item), item.estimated_cost, item.candidate_id),
    )
    explore_ranked = sorted(
        candidates,
        key=lambda item: (
            -item.novelty,
            -active_learning_priority(item),
            item.estimated_cost,
            item.candidate_id,
        ),
    )
    explore_slots = min(slots, max(1, floor(slots * exploration_ratio)))
    exploit_slots = slots - explore_slots
    selected: list[tuple[LearningCandidate, LearningMode]] = []
    selected_ids: set[str] = set()
    spent = 0

    def take(ranked: list[LearningCandidate], limit: int, mode: LearningMode) -> None:
        nonlocal spent
        for candidate in ranked:
            if len([item for item in selected if item[1] is mode]) >= limit:
                break
            if candidate.candidate_id in selected_ids or spent + candidate.estimated_cost > budget:
                continue
            selected.append((candidate, mode))
            selected_ids.add(candidate.candidate_id)
            spent += candidate.estimated_cost

    take(exploit_ranked, exploit_slots, LearningMode.EXPLOIT)
    take(explore_ranked, explore_slots, LearningMode.EXPLORE)
    # If one lane lacks affordable work, fill its unused capacity from the other lane.
    for candidate in exploit_ranked:
        if len(selected) >= slots:
            break
        if candidate.candidate_id in selected_ids or spent + candidate.estimated_cost > budget:
            continue
        selected.append((candidate, LearningMode.EXPLOIT))
        selected_ids.add(candidate.candidate_id)
        spent += candidate.estimated_cost
    return selected, spent


def plan_curriculum(
    candidates: list[LearningCandidate],
    *,
    max_items: int,
    budget_limit: int,
    external_ratio: float = 0.65,
    exploration_ratio: float = 0.20,
    min_intent_relevance: float = 0.30,
) -> CurriculumPlan:
    """Build a deterministic, bounded 65/35 active-learning curriculum."""
    if max_items < 0 or budget_limit < 0:
        raise ValueError("max_items and budget_limit must not be negative")
    if not 0.0 <= external_ratio <= 1.0 or not 0.0 <= exploration_ratio <= 1.0:
        raise ValueError("ratios must be between 0 and 1")
    if not 0.0 <= min_intent_relevance <= 1.0:
        raise ValueError("min_intent_relevance must be between 0 and 1")

    unique, rejected = _deduplicate(candidates, min_intent_relevance)
    external_slots = floor(max_items * external_ratio)
    internal_slots = max_items - external_slots
    external_budget = floor(budget_limit * external_ratio)
    internal_budget = budget_limit - external_budget
    external, external_spent = _select_pool(
        [item for item in unique if item.origin is LearningOrigin.EXTERNAL],
        slots=external_slots,
        budget=external_budget,
        exploration_ratio=exploration_ratio,
    )
    internal, internal_spent = _select_pool(
        [item for item in unique if item.origin is LearningOrigin.INTERNAL],
        slots=internal_slots,
        budget=internal_budget,
        exploration_ratio=exploration_ratio,
    )
    chosen = external + internal
    chosen_ids = {candidate.candidate_id for candidate, _ in chosen}
    rejected.update(candidate.candidate_id for candidate in unique if candidate.candidate_id not in chosen_ids)
    items = tuple(
        CurriculumItem(
            candidate_id=candidate.candidate_id,
            origin=candidate.origin,
            mode=mode,
            priority=active_learning_priority(candidate),
            estimated_cost=candidate.estimated_cost,
            reason=(
                "NOVEL_FRONTIER_EXPLORATION"
                if mode is LearningMode.EXPLORE
                else "GAP_FAILURE_INTENT_PRIORITY"
            ),
        )
        for candidate, mode in chosen
    )
    return CurriculumPlan(
        items=items,
        budget_limit=budget_limit,
        budget_spent=external_spent + internal_spent,
        external_slots=external_slots,
        internal_slots=internal_slots,
        rejected_ids=tuple(sorted(rejected)),
    )
