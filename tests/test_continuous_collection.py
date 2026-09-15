import pytest

from apf.continuous_collection import (
    CollectionCandidate,
    ContinuousCollectionPolicy,
    decide_collection,
    startup_plan,
)
from apf.external_learning import SourceKind


def candidate(**changes) -> CollectionCandidate:
    values = {
        "source_id": "official-standard",
        "kind": SourceKind.OFFICIAL_STANDARD,
        "locator": "https://example.org/standard",
        "intent_relevance": 0.9,
        "license_clarity": 0.9,
    }
    values.update(changes)
    return CollectionCandidate(**values)


def test_default_plan_starts_at_boot_and_collects_immediately():
    plan = startup_plan(ContinuousCollectionPolicy())
    assert plan.start_on_boot
    assert plan.first_collection_delay_seconds == 0
    assert plan.repeat_interval_seconds == 900


def test_private_or_owned_source_requires_explicit_authorization():
    decision = decide_collection(
        candidate(kind=SourceKind.OWNED, explicitly_authorized=False),
        ContinuousCollectionPolicy(),
    )
    assert decision.reason == "EXPLICIT_AUTHORIZATION_REQUIRED"
    assert not decision.collect


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"contains_personal_data": True}, "PERSONAL_DATA_BLOCKED"),
        ({"requires_credentials": True}, "CREDENTIAL_ACCESS_BLOCKED"),
        ({"robots_allowed": False}, "SOURCE_POLICY_BLOCKED"),
        ({"terms_allowed": False}, "SOURCE_POLICY_BLOCKED"),
        ({"content_hash_seen": True}, "DUPLICATE_CONTENT"),
        ({"intent_relevance": 0.29}, "LOW_INTENT_RELEVANCE"),
    ],
)
def test_collection_stops_at_governance_boundaries(changes, reason):
    decision = decide_collection(candidate(**changes), ContinuousCollectionPolicy())
    assert not decision.collect
    assert decision.reason == reason


def test_unclear_license_is_reference_only_not_reusable_asset():
    decision = decide_collection(candidate(license_clarity=0.4), ContinuousCollectionPolicy())
    assert decision.collect
    assert not decision.reusable
    assert decision.reason == "COLLECT_REFERENCE_ONLY"


def test_collection_ratios_must_be_complete():
    with pytest.raises(ValueError, match="ratios must total 1"):
        ContinuousCollectionPolicy(external_target_ratio=0.65, internal_target_ratio=0.20)
