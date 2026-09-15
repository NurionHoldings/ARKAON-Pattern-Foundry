from pathlib import Path
from threading import Event

from apf.collector_runtime import (
    CollectorRuntime,
    MemoryAuditSink,
    MemoryContentHashStore,
    load_policy,
)
from apf.continuous_collection import CollectionCandidate, ContinuousCollectionPolicy
from apf.external_learning import SourceKind


class Provider:
    def __init__(self, *values: CollectionCandidate) -> None:
        self.values = values

    def candidates(self):
        return self.values


class Fetcher:
    def __init__(self, payload: bytes = b"reference") -> None:
        self.payload = payload
        self.calls = 0

    def fetch(self, candidate, max_bytes):
        self.calls += 1
        return self.payload


def candidate(**changes) -> CollectionCandidate:
    values = {
        "source_id": "standard",
        "kind": SourceKind.OFFICIAL_STANDARD,
        "locator": "https://example.org/standard",
        "intent_relevance": 0.9,
        "license_clarity": 0.9,
    }
    values.update(changes)
    return CollectionCandidate(**values)


def test_default_config_loads_boot_collection_policy():
    path = Path(__file__).parents[1] / "config" / "collector.default.json"
    policy = load_policy(path)
    assert policy.enabled
    assert policy.collect_immediately
    assert policy.interval_seconds == 900


def test_secret_candidate_is_audited_without_fetching_content():
    fetcher = Fetcher()
    audit = MemoryAuditSink()
    runtime = CollectorRuntime(
        ContinuousCollectionPolicy(), Provider(candidate(contains_secrets=True)), fetcher, audit
    )
    result = runtime.run_once()
    assert result.denied == 1
    assert fetcher.calls == 0
    assert audit.events[0].decision == "SECRET_CONTENT_BLOCKED"


def test_runtime_deduplicates_fetched_content_and_audits_every_decision():
    fetcher = Fetcher()
    audit = MemoryAuditSink()
    runtime = CollectorRuntime(
        ContinuousCollectionPolicy(), Provider(candidate(), candidate(source_id="mirror")), fetcher, audit
    )
    result = runtime.run_once()
    assert result.collected == 1
    assert result.duplicate == 1
    assert len(audit.events) == 2
    assert audit.events[1].decision == "DUPLICATE_CONTENT"


def test_runtime_uses_injected_hash_store_across_instances():
    hashes = MemoryContentHashStore()
    first = CollectorRuntime(
        ContinuousCollectionPolicy(), Provider(candidate()), Fetcher(), MemoryAuditSink(),
        content_hashes=hashes,
    )
    second = CollectorRuntime(
        ContinuousCollectionPolicy(), Provider(candidate()), Fetcher(), MemoryAuditSink(),
        content_hashes=hashes,
    )
    assert first.run_once().collected == 1
    assert second.run_once().duplicate == 1


def test_oversized_response_is_not_collected():
    policy = ContinuousCollectionPolicy(max_response_bytes=3)
    audit = MemoryAuditSink()
    runtime = CollectorRuntime(policy, Provider(candidate()), Fetcher(b"four"), audit)
    result = runtime.run_once()
    assert result.denied == 1
    assert result.collected == 0
    assert audit.events[0].decision == "RESPONSE_TOO_LARGE"


def test_disabled_runtime_does_not_start_collection_loop():
    fetcher = Fetcher()
    runtime = CollectorRuntime(
        ContinuousCollectionPolicy(enabled=False), Provider(candidate()), fetcher, MemoryAuditSink()
    )
    runtime.run_forever(Event())
    assert fetcher.calls == 0
