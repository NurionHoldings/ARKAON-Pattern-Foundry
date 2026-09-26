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
    selected_external_items: int
    selected_internal_items: int
    external_cost: int
    internal_cost: int
    external_item_ratio: float
    external_cost_ratio: float
    external_item_drift: float
    external_cost_drift: float
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
    explore_slots = (
        0
        if exploration_ratio == 0
        else min(slots, max(1, floor(slots * exploration_ratio)))
    )
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
    max_items: int | None,
    budget_limit: int | None,
    external_ratio: float = 0.65,
    exploration_ratio: float = 0.20,
    min_intent_relevance: float = 0.30,
    prior_external_items: int = 0,
    prior_internal_items: int = 0,
    prior_external_cost: int = 0,
    prior_internal_cost: int = 0,
) -> CurriculumPlan:
    """Build a deterministic 65/35 active-learning curriculum (unbounded when limits are None)."""
    if (max_items is not None and max_items < 0) or (budget_limit is not None and budget_limit < 0):
        raise ValueError("max_items and budget_limit must not be negative")
    if min(
        prior_external_items,
        prior_internal_items,
        prior_external_cost,
        prior_internal_cost,
    ) < 0:
        raise ValueError("prior counts and costs must not be negative")
    if not 0.0 <= external_ratio <= 1.0 or not 0.0 <= exploration_ratio <= 1.0:
        raise ValueError("ratios must be between 0 and 1")
    if not 0.0 <= min_intent_relevance <= 1.0:
        raise ValueError("min_intent_relevance must be between 0 and 1")

    unique, rejected = _deduplicate(candidates, min_intent_relevance)
    if max_items is None:
        max_items = len(unique)
    if budget_limit is None:
        budget_limit = sum(candidate.estimated_cost for candidate in unique) or max(len(unique), 1)
    # Allocate against the cumulative target instead of rounding every batch down.
    # This gives a one-item batch to the external lane while deterministic carry
    # makes later batches repay the internal baseline (65/35 over time).
    prior_items = prior_external_items + prior_internal_items
    target_external_items = floor((prior_items + max_items) * external_ratio + 0.5)
    external_slots = min(max_items, max(0, target_external_items - prior_external_items))
    internal_slots = max_items - external_slots
    prior_cost = prior_external_cost + prior_internal_cost
    target_external_cost = floor((prior_cost + budget_limit) * external_ratio + 0.5)
    external_budget = min(budget_limit, max(0, target_external_cost - prior_external_cost))
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

    # A missing/expensive lane must not leave safe capacity idle. Reallocate only
    # this batch's unused capacity; cumulative carry keeps the absent lane's
    # deficit, so the 35% internal baseline cannot silently disappear.
    chosen_ids = {candidate.candidate_id for candidate, _ in external + internal}
    remaining_slots = max_items - len(chosen_ids)
    remaining_budget = budget_limit - external_spent - internal_spent
    if remaining_slots and remaining_budget:
        overflow, overflow_spent = _select_pool(
            [candidate for candidate in unique if candidate.candidate_id not in chosen_ids],
            slots=remaining_slots,
            budget=remaining_budget,
            exploration_ratio=exploration_ratio,
        )
        external.extend(item for item in overflow if item[0].origin is LearningOrigin.EXTERNAL)
        internal.extend(item for item in overflow if item[0].origin is LearningOrigin.INTERNAL)
        external_spent += sum(
            item.estimated_cost
            for item, _ in overflow
            if item.origin is LearningOrigin.EXTERNAL
        )
        internal_spent += sum(
            item.estimated_cost
            for item, _ in overflow
            if item.origin is LearningOrigin.INTERNAL
        )
        assert overflow_spent == sum(item.estimated_cost for item, _ in overflow)
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
    selected_external_items = len(external)
    selected_internal_items = len(internal)
    selected_items = selected_external_items + selected_internal_items
    selected_cost = external_spent + internal_spent
    external_item_ratio = (
        round(selected_external_items / selected_items, 6) if selected_items else 0.0
    )
    external_cost_ratio = round(external_spent / selected_cost, 6) if selected_cost else 0.0
    return CurriculumPlan(
        items=items,
        budget_limit=budget_limit,
        budget_spent=selected_cost,
        external_slots=external_slots,
        internal_slots=internal_slots,
        selected_external_items=selected_external_items,
        selected_internal_items=selected_internal_items,
        external_cost=external_spent,
        internal_cost=internal_spent,
        external_item_ratio=external_item_ratio,
        external_cost_ratio=external_cost_ratio,
        external_item_drift=round(external_item_ratio - external_ratio, 6),
        external_cost_drift=round(external_cost_ratio - external_ratio, 6),
        rejected_ids=tuple(sorted(rejected)),
    )
