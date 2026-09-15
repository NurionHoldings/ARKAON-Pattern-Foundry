import pytest

from apf.asset_registry import (
    AssetPromotionDenied,
    AssetRecord,
    ConceptVerification,
    build_assetization_report,
    promote,
)
from apf.continuous_collection import AssetLifecycle


def record(**changes):
    values = {
        "asset_id": "asset-1",
        "source_id": "official-source",
        "title": "Reusable retry principle",
        "stage": AssetLifecycle.REFERENCE_COLLECTED,
        "provenance_ref": "evidence:source-1",
    }
    values.update(changes)
    return AssetRecord(**values)


class Reports:
    def __init__(self):
        self.values = []

    def publish(self, report):
        self.values.append(report)


class Ethernian:
    def __init__(self, decision="PASS"):
        self.decision = decision

    def verify(self, report):
        return ConceptVerification(
            verifier="ETHERNIAN",
            decision=self.decision,
            checks=("provenance", "clean-room", "intent-alignment"),
        )


def test_asset_must_advance_sequentially():
    with pytest.raises(AssetPromotionDenied, match="NON_SEQUENTIAL"):
        promote(record(), AssetLifecycle.OWNED_ASSET)


def test_each_new_asset_concept_publishes_an_immediate_report():
    reports = Reports()
    conceptualized = promote(
        record(principle_ref="principle:retry-with-jitter"),
        AssetLifecycle.PRINCIPLE_ABSTRACTED,
        report_sink=reports,
        ethernian_verifier=Ethernian(),
    )
    assert conceptualized.stage == AssetLifecycle.PRINCIPLE_ABSTRACTED
    assert len(reports.values) == 1
    assert reports.values[0].report_type == "NEW_ASSET_CONCEPTUALIZED"
    assert reports.values[0].principle_ref == "principle:retry-with-jitter"


def test_failed_ethernian_review_prevents_promotion_and_user_report():
    reports = Reports()
    with pytest.raises(AssetPromotionDenied, match="ETHERNIAN_VERIFICATION_FAILED"):
        promote(
            record(principle_ref="principle:unsafe"),
            AssetLifecycle.PRINCIPLE_ABSTRACTED,
            report_sink=reports,
            ethernian_verifier=Ethernian("FAIL"),
        )
    assert reports.values == []


def test_independent_route_requires_principle_implementation_tests_and_human_approval():
    value = promote(
        record(principle_ref="principle:1"),
        AssetLifecycle.PRINCIPLE_ABSTRACTED,
        report_sink=Reports(),
        ethernian_verifier=Ethernian(),
    )
    value = promote(
        value.__class__(**{**value.__dict__, "implementation_ref": "src/retry.py"}),
        AssetLifecycle.INDEPENDENT_IMPLEMENTATION,
    )
    value = promote(
        value.__class__(**{**value.__dict__, "test_refs": ("tests/test_retry.py",)}),
        AssetLifecycle.INDEPENDENTLY_VERIFIED,
    )
    with pytest.raises(AssetPromotionDenied, match="HUMAN_APPROVAL_REQUIRED"):
        promote(value, AssetLifecycle.OWNED_ASSET)
    approved = promote(
        value.__class__(**{**value.__dict__, "approval_ref": "approval:human-1"}),
        AssetLifecycle.OWNED_ASSET,
    )
    assert approved.stage == AssetLifecycle.OWNED_ASSET


def test_source_code_copy_cannot_be_promoted_as_independent_implementation():
    value = record(
        stage=AssetLifecycle.PRINCIPLE_ABSTRACTED,
        principle_ref="principle:1",
        implementation_ref="src/copied.py",
        copied_source_code=True,
    )
    with pytest.raises(AssetPromotionDenied, match="INDEPENDENT_IMPLEMENTATION_REQUIRED"):
        promote(value, AssetLifecycle.INDEPENDENT_IMPLEMENTATION)


def test_report_counts_every_stage_without_inflating_owned_assets():
    report = build_assetization_report(
        [record(), record(asset_id="asset-2", stage=AssetLifecycle.OWNED_ASSET)]
    )
    assert report.total == 2
    assert report.by_stage["REFERENCE_COLLECTED"] == 1
    assert report.by_stage["OWNED_ASSET"] == 1
    assert report.owned_assets == ("asset-2",)
