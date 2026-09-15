import copy
import json
from pathlib import Path

import pytest

from apf.analog_synthesis import (
    AnalogSynthesisError,
    OnceTransitionModel,
    ScopedAuthorityModel,
    TrustedMoneyModel,
    validate_analog_manifest,
)

MANIFEST = Path(__file__).parents[1] / "knowledge" / "synthesis" / "mjn-analog-031.json"


def load_document():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def encode(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def test_checked_in_manifest_has_independent_sources_and_locked_outcome():
    result = validate_analog_manifest(MANIFEST.read_bytes())
    assert len(result.source_families) == 4
    assert len(result.source_lineages) == 3
    assert set(result.candidate_names) == {
        "principal-ownership-recheck",
        "transactional-idempotent-transition",
        "financial-sot-audit-chain",
    }
    assert result.role_flow == ("RESEARCH", "ANALYZE", "ARCHITECT", "BUILD", "TEST", "AUDIT")
    assert result.owned_asset is False
    assert result.mutation_allowed is False


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda d: d["boundaries"].update(mjn_read_only=False), "CLEAN_ROOM_BOUNDARY"),
        (lambda d: d["boundaries"].update(promote_owned_asset=True), "CLEAN_ROOM_BOUNDARY"),
        (lambda d: d["candidates"][0].update(owned_asset=True), "UNSAFE_CANDIDATE"),
        (lambda d: d["candidates"][0].update(review_status="APPROVED"), "UNSAFE_CANDIDATE"),
        (lambda d: d["sources"][0].update(authority="BLOG"), "UNTRUSTED_SOURCE"),
        (lambda d: d["sources"][0].update(content_digest="sha256:" + "0" * 64), "SOURCE_EVIDENCE_MISMATCH"),
        (lambda d: d["mjn_input"].update(write_allowed=True), "INVALID_MJN_INPUT"),
        (lambda d: d.update(quoted_text="copied phrase"), "INVALID_MANIFEST_SCHEMA"),
    ],
)
def test_manifest_fails_closed_on_provenance_or_boundary_tampering(mutate, code):
    document = load_document()
    mutate(document)
    with pytest.raises(AnalogSynthesisError, match=code):
        validate_analog_manifest(encode(document))


def test_single_external_source_without_first_party_support_is_rejected():
    document = load_document()
    candidate = document["candidates"][0]
    candidate["mjn_evidence_refs"] = []
    with pytest.raises(AnalogSynthesisError, match="SOURCE_DOMINANCE"):
        validate_analog_manifest(encode(document))


def test_one_provider_cannot_fake_independence_with_multiple_document_families():
    document = load_document()
    for source in document["sources"]:
        source["lineage"] = "one-provider"
    with pytest.raises(AnalogSynthesisError, match="THREE_SOURCE_FAMILIES_REQUIRED"):
        validate_analog_manifest(encode(document))


@pytest.mark.parametrize(
    "leaked",
    ["Built like OpenFGA", "see https://example.test", "Temporal workflow clone"],
)
def test_generated_material_rejects_source_identity_or_url_leakage(leaked):
    document = load_document()
    document["candidates"][0]["process_steps"].append(leaked)
    with pytest.raises(AnalogSynthesisError, match="LEAKAGE"):
        validate_analog_manifest(encode(document))


def test_scoped_authority_reference_model_checks_current_owner_and_status():
    assert ScopedAuthorityModel.may_use(
        actor="worker-a", owner="worker-a", active=True, requested_owner="worker-a"
    )
    assert not ScopedAuthorityModel.may_use(
        actor="worker-a", owner="worker-b", active=True, requested_owner="worker-b"
    )
    assert not ScopedAuthorityModel.may_use(
        actor="worker-a", owner="worker-a", active=False, requested_owner="worker-a"
    )
    assert not ScopedAuthorityModel.may_use(
        actor="worker-a", owner="worker-a", active=True, requested_owner="worker-b"
    )


def test_once_transition_reference_model_replays_and_rejects_conflicts():
    model = OnceTransitionModel()
    receipt = model.apply(actor="worker-a", key="retry-1", intent_digest="intent-a")
    assert model.apply(actor="worker-a", key="retry-1", intent_digest="intent-a") == receipt
    with pytest.raises(AnalogSynthesisError, match="IDEMPOTENCY_INTENT_CONFLICT"):
        model.apply(actor="worker-a", key="retry-1", intent_digest="intent-b")
    with pytest.raises(AnalogSynthesisError, match="TERMINAL_STATE_CONFLICT"):
        model.apply(actor="worker-b", key="retry-2", intent_digest="intent-a")


def test_trusted_money_reference_model_ignores_client_and_freezes_snapshot():
    model = TrustedMoneyModel()
    first = model.settle(
        order_id="order-a",
        actor="system-a",
        verified_paid_amount=10_000,
        policy_fee=1_000,
        client_amount=1,
    )
    replay = model.settle(
        order_id="order-a",
        actor="system-a",
        verified_paid_amount=10_000,
        policy_fee=1_000,
        client_amount=99_999,
    )
    assert first == replay == (10_000, 9_000)
    assert model.audit == [("system-a", "order-a")]
    with pytest.raises(AnalogSynthesisError, match="IMMUTABLE_SETTLEMENT_CONFLICT"):
        model.settle(
            order_id="order-a",
            actor="system-a",
            verified_paid_amount=10_000,
            policy_fee=2_000,
        )
    with pytest.raises(AnalogSynthesisError, match="UNTRUSTED_FINANCIAL_TRANSITION"):
        model.settle(
            order_id="order-b",
            actor="system-a",
            verified_paid_amount=10_000,
            policy_fee=1_000,
            payment_reversed=True,
        )


def test_duplicate_json_fields_are_rejected():
    raw = MANIFEST.read_text(encoding="utf-8")
    tampered = raw.replace(
        '"schema_version": "apf.clean-room-analog-synthesis/v1",',
        '"schema_version": "apf.clean-room-analog-synthesis/v1", "schema_version": "x",',
        1,
    )
    with pytest.raises(AnalogSynthesisError, match="DUPLICATE_JSON_FIELD"):
        validate_analog_manifest(tampered.encode())


def test_candidate_evidence_cannot_reference_an_unregistered_digest():
    document = copy.deepcopy(load_document())
    document["candidates"][1]["external_evidence_refs"] = ["sha256:" + "9" * 64]
    with pytest.raises(AnalogSynthesisError, match="UNSAFE_CANDIDATE"):
        validate_analog_manifest(encode(document))
