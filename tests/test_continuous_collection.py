import pytest

from apf.continuous_collection import (
    AssetizationBasis,
    AssetLifecycle,
    CollectionCandidate,
    ContinuousCollectionPolicy,
    assetization_route,
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
        ({"contains_secrets": True}, "SECRET_CONTENT_BLOCKED"),
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
    assert decision.reason == "COLLECT_REFERENCE_FOR_INDEPENDENT_DEVELOPMENT"


def test_unclear_license_can_be_assetized_by_clean_room_exception():
    decision = decide_collection(
        candidate(
            license_clarity=0.4,
            assetization_basis=AssetizationBasis.CLEAN_ROOM_ABSTRACTION,
            provenance_recorded=True,
            copied_source_code=False,
            rights_review_passed=True,
            owner_approval_digest="sha256:" + "a" * 64,
            independent_implementation=True,
            original_expression_excluded=True,
            distinctive_category_count=2,
            functional_distinction=True,
            similarity_review_passed=True,
        ),
        ContinuousCollectionPolicy(),
    )
    assert decision.collect
    assert decision.reusable
    assert decision.reason == "COLLECT_INDEPENDENT_ASSET"


def test_assetization_exception_requires_provenance_and_no_code_copy():
    no_provenance = decide_collection(
        candidate(
            license_clarity=0.4,
            assetization_basis=AssetizationBasis.CLEAN_ROOM_ABSTRACTION,
            provenance_recorded=False,
        ),
        ContinuousCollectionPolicy(),
    )
    copied = decide_collection(
        candidate(
            license_clarity=0.4,
            assetization_basis=AssetizationBasis.CLEAN_ROOM_ABSTRACTION,
            provenance_recorded=True,
            copied_source_code=True,
        ),
        ContinuousCollectionPolicy(),
    )
    assert not no_provenance.reusable
    assert not copied.reusable


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rights_review_passed", False),
        ("owner_approval_digest", None),
        ("independent_implementation", False),
        ("original_expression_excluded", False),
        ("distinctive_category_count", 1),
        ("functional_distinction", False),
        ("similarity_review_passed", False),
    ],
)
def test_clean_room_exception_fails_closed_when_a_concrete_gate_is_missing(field, value):
    controls = {
        "license_clarity": 0.4,
        "assetization_basis": AssetizationBasis.CLEAN_ROOM_ABSTRACTION,
        "provenance_recorded": True,
        "copied_source_code": False,
        "rights_review_passed": True,
        "owner_approval_digest": "sha256:" + "a" * 64,
        "independent_implementation": True,
        "original_expression_excluded": True,
        "distinctive_category_count": 2,
        "functional_distinction": True,
        "similarity_review_passed": True,
    }
    controls[field] = value
    decision = decide_collection(candidate(**controls), ContinuousCollectionPolicy())
    assert decision.collect
    assert not decision.reusable
    assert decision.reason == "COLLECT_REFERENCE_FOR_INDEPENDENT_DEVELOPMENT"


def test_collection_ratios_must_be_complete():
    with pytest.raises(ValueError, match="ratios must total 1"):
        ContinuousCollectionPolicy(external_target_ratio=0.65, internal_target_ratio=0.20)


def test_reference_advances_to_abstraction_then_independent_build():
    reference = assetization_route(AssetLifecycle.REFERENCE_COLLECTED)
    abstracted = assetization_route(reference.next_step)
    assert reference.next_step == AssetLifecycle.PRINCIPLE_ABSTRACTED
    assert abstracted.next_step == AssetLifecycle.INDEPENDENT_IMPLEMENTATION
    assert not reference.may_publish_as_owned


def test_only_completed_independent_route_becomes_owned_asset():
    verified = assetization_route(AssetLifecycle.INDEPENDENTLY_VERIFIED)
    owned = assetization_route(verified.next_step)
    assert verified.next_step == AssetLifecycle.OWNED_ASSET
    assert owned.may_publish_as_owned
    assert owned.next_step is None
