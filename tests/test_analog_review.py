from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apf.analog_review import (
    AnalogReviewError,
    AnalogReviewEvaluator,
    AnalogReviewPacketBuilder,
    EthernianReviewSigner,
    ReviewOutcome,
    ReviewVerdict,
)

MANIFEST = Path(__file__).parents[1] / "knowledge" / "synthesis" / "mjn-analog-031.json"
NOW = datetime(2031, 1, 1, tzinfo=UTC)
REVISION = "542d252"
POLICY = "apf-review-policy/v1"


@pytest.fixture
def packets():
    return AnalogReviewPacketBuilder.build(
        MANIFEST.read_bytes(), policy_version=POLICY, revision=REVISION
    )


@pytest.fixture
def authorities():
    private = Ed25519PrivateKey.generate()
    return EthernianReviewSigner(private), AnalogReviewEvaluator(
        private.public_key(), now_provider=lambda: NOW
    )


def test_checked_in_candidates_produce_deterministic_immutable_packets(packets):
    again = AnalogReviewPacketBuilder.build(
        MANIFEST.read_bytes(), policy_version=POLICY, revision=REVISION
    )
    assert packets == again
    assert [item.candidate_name for item in packets] == [
        "principal-ownership-recheck",
        "transactional-idempotent-transition",
        "financial-sot-audit-chain",
    ]
    assert len({item.fingerprint for item in packets}) == 3
    assert all(len(item.checks) == 7 and all(passed for _, passed in item.checks) for item in packets)


@pytest.mark.parametrize(
    ("verdict", "outcome"),
    [
        (ReviewVerdict.APPROVE, ReviewOutcome.APPROVED_FOR_PATTERN_PROMOTION),
        (ReviewVerdict.REVIEW, ReviewOutcome.ETHERNIAN_REVIEW_REQUIRED),
        (ReviewVerdict.DENY, ReviewOutcome.DENIED),
    ],
)
def test_external_decision_maps_without_asset_or_write_promotion(
    packets, authorities, verdict, outcome
):
    signer, evaluator = authorities
    decision = signer.sign(
        packets[0],
        verdict=verdict,
        expires_at=NOW + timedelta(hours=1),
        nonce=f"00000000-0000-0000-0000-0000000000{len(verdict):02d}",
    )
    accepted = evaluator.accept(packets[0], decision)
    assert accepted.outcome is outcome
    assert accepted.owned_asset is False
    assert accepted.intent_dna_mutation_allowed is False
    assert accepted.mjn_write_allowed is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_fingerprint", "sha256:" + "0" * 64),
        ("candidate_name", "wrong-candidate"),
        ("content_digest", "sha256:" + "1" * 64),
        ("lineage_digest", "sha256:" + "2" * 64),
        ("policy_version", "wrong-policy"),
        ("revision", "deadbeef"),
        ("packet_fingerprint", "sha256:" + "3" * 64),
    ],
)
def test_all_review_bindings_are_fail_closed(packets, authorities, field, value):
    signer, evaluator = authorities
    decision = signer.sign(
        packets[0],
        verdict=ReviewVerdict.APPROVE,
        expires_at=NOW + timedelta(hours=1),
        nonce="00000000-0000-0000-0000-000000000031",
    )
    with pytest.raises(AnalogReviewError, match="REVIEW_BINDING_MISMATCH"):
        evaluator.accept(packets[0], replace(decision, **{field: value}))


def test_tamper_wrong_key_expiry_and_replay_are_blocked(packets):
    signing_key = Ed25519PrivateKey.generate()
    signer = EthernianReviewSigner(signing_key)
    decision = signer.sign(
        packets[0],
        verdict=ReviewVerdict.APPROVE,
        expires_at=NOW + timedelta(hours=1),
        nonce="00000000-0000-0000-0000-000000000031",
    )
    wrong = AnalogReviewEvaluator(
        Ed25519PrivateKey.generate().public_key(), now_provider=lambda: NOW
    )
    with pytest.raises(AnalogReviewError, match="INVALID_ETHERNIAN_SIGNATURE"):
        wrong.accept(packets[0], decision)

    evaluator = AnalogReviewEvaluator(signing_key.public_key(), now_provider=lambda: NOW)
    tampered = replace(decision, verdict=ReviewVerdict.DENY)
    with pytest.raises(AnalogReviewError, match="INVALID_ETHERNIAN_SIGNATURE"):
        evaluator.accept(packets[0], tampered)
    evaluator.accept(packets[0], decision)
    with pytest.raises(AnalogReviewError, match="REVIEW_REPLAY_BLOCKED"):
        evaluator.accept(packets[0], decision)

    expired = signer.sign(
        packets[1],
        verdict=ReviewVerdict.REVIEW,
        expires_at=NOW,
        nonce="00000000-0000-0000-0000-000000000032",
    )
    with pytest.raises(AnalogReviewError, match="REVIEW_DECISION_EXPIRED"):
        evaluator.accept(packets[1], expired)


def test_decision_for_one_candidate_cannot_approve_another(packets, authorities):
    signer, evaluator = authorities
    decision = signer.sign(
        packets[0],
        verdict=ReviewVerdict.APPROVE,
        expires_at=NOW + timedelta(hours=1),
        nonce="00000000-0000-0000-0000-000000000031",
    )
    with pytest.raises(AnalogReviewError, match="REVIEW_BINDING_MISMATCH"):
        evaluator.accept(packets[1], decision)


def test_unknown_verdict_fails_closed_even_if_externally_signed(packets):
    key = Ed25519PrivateKey.generate()
    signer = EthernianReviewSigner(key)
    evaluator = AnalogReviewEvaluator(key.public_key(), now_provider=lambda: NOW)
    decision = signer.sign(
        packets[0],
        verdict="UNKNOWN",  # type: ignore[arg-type]
        expires_at=NOW + timedelta(hours=1),
        nonce="00000000-0000-0000-0000-000000000031",
    )
    with pytest.raises(AnalogReviewError, match="INVALID_REVIEW_VERDICT"):
        evaluator.accept(packets[0], decision)


def test_incomplete_or_failed_packet_checks_cannot_be_approved(packets, authorities):
    signer, evaluator = authorities
    bad_packet = replace(packets[0], checks=packets[0].checks[:-1])
    decision = signer.sign(
        bad_packet,
        verdict=ReviewVerdict.APPROVE,
        expires_at=NOW + timedelta(hours=1),
        nonce="00000000-0000-0000-0000-000000000031",
    )
    with pytest.raises(AnalogReviewError, match="REVIEW_PACKET_CHECK_FAILED"):
        evaluator.accept(bad_packet, decision)
