from apf.external_learning import (
    LearningSource,
    SourceKind,
    may_create_reusable_derivative,
    plan_learning,
)


def source(source_id: str, kind: SourceKind, **changes) -> LearningSource:
    values = {
        "source_id": source_id,
        "kind": kind,
        "domain": "workflow",
        "intent_relevance": 0.9,
        "authority": 0.9,
        "license_clarity": 0.9,
        "recency": 0.8,
        "novelty": 0.8,
        "derivation_allowed": True,
    }
    values.update(changes)
    return LearningSource(**values)


def test_learning_budget_reserves_internal_baseline():
    sources = [
        source("internal-1", SourceKind.OWNED),
        source("internal-2", SourceKind.OWNED),
        source("standard", SourceKind.OFFICIAL_STANDARD),
        source("docs", SourceKind.OFFICIAL_DOCUMENTATION),
        source("oss", SourceKind.LICENSED_OPEN_SOURCE),
    ]
    plan = plan_learning(sources, max_sources=4)
    assert sum(p.reason == "EXTERNAL_PRIORITY" for p in plan) == 2
    assert sum(p.reason == "INTENT_RELEVANT_INTERNAL_BASELINE" for p in plan) == 2


def test_unavailable_internal_capacity_is_filled_by_external_sources():
    sources = [
        source(f"external-{index}", SourceKind.OFFICIAL_STANDARD)
        for index in range(5)
    ]
    plan = plan_learning(sources, max_sources=4)
    assert len(plan) == 4
    assert all(p.reason == "EXTERNAL_PRIORITY" for p in plan)


def test_ten_slot_budget_tracks_65_35_target_without_erasing_baseline():
    sources = [
        *[source(f"external-{index}", SourceKind.OFFICIAL_STANDARD) for index in range(10)],
        *[source(f"internal-{index}", SourceKind.OWNED) for index in range(10)],
    ]
    plan = plan_learning(sources, max_sources=10)
    assert sum(p.reason == "EXTERNAL_PRIORITY" for p in plan) == 6
    assert sum(p.reason == "INTENT_RELEVANT_INTERNAL_BASELINE" for p in plan) == 4


def test_seen_and_irrelevant_sources_are_skipped():
    sources = [
        source("seen", SourceKind.OFFICIAL_STANDARD, content_hash_seen=True),
        source("irrelevant", SourceKind.OFFICIAL_STANDARD, intent_relevance=0.29),
    ]
    assert plan_learning(sources, max_sources=5) == []


def test_unclear_license_cannot_create_derivative():
    item = source("unclear", SourceKind.LICENSED_OPEN_SOURCE, license_clarity=0.4)
    assert not may_create_reusable_derivative(item)

