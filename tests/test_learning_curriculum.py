import pytest

from apf.learning_curriculum import (
    LearningCandidate,
    LearningMode,
    LearningOrigin,
    active_learning_priority,
    plan_curriculum,
)


def candidate(
    candidate_id: str,
    origin: LearningOrigin,
    *,
    gap: float = 0.8,
    failures: float = 0.7,
    relevance: float = 0.9,
    novelty: float = 0.5,
    cost: int = 1,
    fingerprint: str | None = None,
    learned: bool = False,
) -> LearningCandidate:
    return LearningCandidate(
        candidate_id=candidate_id,
        origin=origin,
        knowledge_gap=gap,
        failure_frequency=failures,
        intent_relevance=relevance,
        novelty=novelty,
        estimated_cost=cost,
        content_fingerprint=fingerprint,
        already_learned=learned,
    )


def test_curriculum_reserves_external_65_internal_35_slots() -> None:
    candidates = [candidate(f"e-{index:02}", LearningOrigin.EXTERNAL) for index in range(20)]
    candidates += [candidate(f"i-{index:02}", LearningOrigin.INTERNAL) for index in range(20)]

    plan = plan_curriculum(candidates, max_items=20, budget_limit=20)

    assert plan.external_slots == 13
    assert plan.internal_slots == 7
    assert sum(item.origin is LearningOrigin.EXTERNAL for item in plan.items) == 13
    assert sum(item.origin is LearningOrigin.INTERNAL for item in plan.items) == 7
    assert plan.external_item_ratio == 0.65
    assert plan.external_cost_ratio == 0.65
    assert plan.external_item_drift == 0
    assert plan.external_cost_drift == 0


@pytest.mark.parametrize(
    ("max_items", "external", "internal"),
    [(1, 1, 0), (2, 1, 1), (3, 2, 1), (4, 3, 1), (5, 3, 2)],
)
def test_small_batches_use_deterministic_65_35_carry(
    max_items: int, external: int, internal: int
) -> None:
    candidates = [candidate(f"e-{index}", LearningOrigin.EXTERNAL) for index in range(10)]
    candidates += [candidate(f"i-{index}", LearningOrigin.INTERNAL) for index in range(10)]

    plan = plan_curriculum(candidates, max_items=max_items, budget_limit=max_items)

    assert plan.selected_external_items == external
    assert plan.selected_internal_items == internal


def test_prior_carry_repays_internal_baseline_after_external_first_batch() -> None:
    candidates = [candidate("external", LearningOrigin.EXTERNAL)]
    candidates += [candidate(f"internal-{index}", LearningOrigin.INTERNAL) for index in range(2)]

    plan = plan_curriculum(
        candidates,
        max_items=2,
        budget_limit=2,
        prior_external_items=1,
        prior_external_cost=1,
    )

    assert plan.external_slots == 1
    assert plan.internal_slots == 1
    assert plan.selected_internal_items == 1


def test_missing_lane_reallocates_without_erasing_its_cumulative_deficit() -> None:
    candidates = [candidate(f"e-{index}", LearningOrigin.EXTERNAL) for index in range(4)]

    plan = plan_curriculum(candidates, max_items=4, budget_limit=4)

    assert len(plan.items) == 4
    assert plan.selected_external_items == 4
    assert plan.external_item_drift == pytest.approx(0.35)

    recovery = plan_curriculum(
        [candidate(f"i-{index}", LearningOrigin.INTERNAL) for index in range(4)],
        max_items=2,
        budget_limit=2,
        prior_external_items=plan.selected_external_items,
        prior_internal_items=plan.selected_internal_items,
        prior_external_cost=plan.external_cost,
        prior_internal_cost=plan.internal_cost,
    )
    assert recovery.external_slots == 0
    assert recovery.internal_slots == 2


def test_priority_uses_gap_failures_intent_and_novelty() -> None:
    item = candidate("source", LearningOrigin.EXTERNAL, gap=1, failures=0.8, relevance=0.6, novelty=0.4)

    assert active_learning_priority(item) == pytest.approx(0.76)


def test_duplicate_seen_and_low_relevance_work_is_excluded() -> None:
    candidates = [
        candidate("best", LearningOrigin.EXTERNAL, gap=0.9, fingerprint="same"),
        candidate("duplicate", LearningOrigin.EXTERNAL, gap=0.2, fingerprint="same"),
        candidate("seen", LearningOrigin.INTERNAL, learned=True),
        candidate("off-intent", LearningOrigin.INTERNAL, relevance=0.29),
        candidate("internal", LearningOrigin.INTERNAL),
    ]

    plan = plan_curriculum(candidates, max_items=4, budget_limit=10)

    assert {item.candidate_id for item in plan.items} == {"best", "internal"}
    assert plan.rejected_ids == ("duplicate", "off-intent", "seen")


def test_exploration_preserves_a_novel_frontier() -> None:
    candidates = [
        candidate(f"high-{index}", LearningOrigin.EXTERNAL, gap=1, novelty=0.1)
        for index in range(4)
    ]
    candidates.append(
        candidate("frontier", LearningOrigin.EXTERNAL, gap=0.3, failures=0.1, novelty=1)
    )

    plan = plan_curriculum(
        candidates,
        max_items=5,
        budget_limit=5,
        external_ratio=1,
        exploration_ratio=0.2,
    )

    frontier = next(item for item in plan.items if item.candidate_id == "frontier")
    assert frontier.mode is LearningMode.EXPLORE


def test_budget_is_hard_bounded_and_deterministic() -> None:
    candidates = [
        candidate("external-a", LearningOrigin.EXTERNAL, cost=2),
        candidate("external-b", LearningOrigin.EXTERNAL, gap=0.7, cost=2),
        candidate("internal-a", LearningOrigin.INTERNAL, cost=1),
        candidate("internal-b", LearningOrigin.INTERNAL, gap=0.7, cost=1),
    ]

    first = plan_curriculum(candidates, max_items=4, budget_limit=4)
    second = plan_curriculum(list(reversed(candidates)), max_items=4, budget_limit=4)

    assert first == second
    assert first.budget_spent <= first.budget_limit


def test_invalid_cost_and_metrics_are_rejected() -> None:
    with pytest.raises(ValueError):
        candidate("bad-cost", LearningOrigin.EXTERNAL, cost=0)
    with pytest.raises(ValueError):
        candidate("bad-score", LearningOrigin.EXTERNAL, gap=1.1)
