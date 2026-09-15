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


def test_external_sources_receive_majority_capacity():
    sources = [
        source("internal-1", SourceKind.OWNED),
        source("internal-2", SourceKind.OWNED),
        source("standard", SourceKind.OFFICIAL_STANDARD),
        source("docs", SourceKind.OFFICIAL_DOCUMENTATION),
        source("oss", SourceKind.LICENSED_OPEN_SOURCE),
    ]
    plan = plan_learning(sources, max_sources=4)
    assert sum(p.reason == "EXTERNAL_PRIORITY" for p in plan) >= 3


def test_seen_and_irrelevant_sources_are_skipped():
    sources = [
        source("seen", SourceKind.OFFICIAL_STANDARD, content_hash_seen=True),
        source("irrelevant", SourceKind.OFFICIAL_STANDARD, intent_relevance=0.29),
    ]
    assert plan_learning(sources, max_sources=5) == []


def test_unclear_license_cannot_create_derivative():
    item = source("unclear", SourceKind.LICENSED_OPEN_SOURCE, license_clarity=0.4)
    assert not may_create_reusable_derivative(item)

