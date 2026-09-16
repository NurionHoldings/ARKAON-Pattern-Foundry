import json
from pathlib import Path

import pytest

from apf.owned_platform_metadata import MetadataPilotError, validate_metadata_pilot

ROOT = Path(__file__).parents[1]
MANIFESTS = {
    "NOGADA_NEWS": ROOT / "knowledge/pilots/nogada-news-041.json",
    "SIDEJOB_MARKET": ROOT / "knowledge/pilots/sidejob-market-041.json",
}


def load(platform_id: str) -> dict:
    return json.loads(MANIFESTS[platform_id].read_text(encoding="utf-8"))


def encode(document: dict) -> bytes:
    return json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


@pytest.mark.parametrize(
    ("platform_id", "expected_names"),
    [
        (
            "NOGADA_NEWS",
            (
                "source-provenance-ledger",
                "two-stage-publish-approval",
                "correction-aware-editorial-workflow",
            ),
        ),
        (
            "SIDEJOB_MARKET",
            (
                "constraint-aware-opportunity-matching",
                "participant-earnings-lifecycle",
                "bounded-ai-assistant-delegation",
                "evidence-gated-settlement",
            ),
        ),
    ],
)
def test_checked_in_metadata_pilots_are_deterministic_and_review_locked(
    platform_id, expected_names
):
    result = validate_metadata_pilot(MANIFESTS[platform_id].read_bytes())
    assert result.platform_id == platform_id
    assert result.candidate_names == expected_names
    assert result.status == "ETHERNIAN_REVIEW_REQUIRED"
    assert result.repository_connection == "NOT_RUN_UNAVAILABLE"
    assert result.intent_dna_mutation_allowed is False
    assert result.owned_asset_promotion_allowed is False


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda d: d["platform"].update(name="MJN"), "WRONG_PLATFORM"),
        (lambda d: d.update(pilot_id="APF-PILOT-041-OTHER"), "WRONG_PLATFORM"),
        (
            lambda d: d["authorization"].update(evidence_ref="sha256:" + "0" * 64),
            "AUTHORIZATION_NOT_PROVEN",
        ),
        (
            lambda d: d["collection"]["allowed_surfaces"].append("DATABASE_ROWS"),
            "UNAUTHORIZED_SURFACE_OR_OPERATION",
        ),
        (
            lambda d: d["collection"].update(repository_connection="CONNECTED"),
            "UNAUTHORIZED_SURFACE_OR_OPERATION",
        ),
        (
            lambda d: d["collection"].update(actual_code_analysis=True),
            "UNAUTHORIZED_SURFACE_OR_OPERATION",
        ),
        (
            lambda d: d["collection"]["prohibited"].remove("PII"),
            "UNAUTHORIZED_SURFACE_OR_OPERATION",
        ),
        (
            lambda d: d["collection"]["prohibited"].remove("SECRET"),
            "UNAUTHORIZED_SURFACE_OR_OPERATION",
        ),
        (
            lambda d: d["domain_metadata"]["workflows"].append("INVENTED_FROM_CODE"),
            "FABRICATED_OR_TAMPERED_SOURCE_EVIDENCE",
        ),
        (
            lambda d: d.update(domain_metadata_hash="sha256:" + "1" * 64),
            "FABRICATED_OR_TAMPERED_SOURCE_EVIDENCE",
        ),
        (
            lambda d: d["candidates"][0].update(contains_source_material=True),
            "CANDIDATE_LEAKAGE_OR_STATUS",
        ),
        (
            lambda d: d["candidates"][0].update(status="OWNED_ASSET"),
            "CANDIDATE_LEAKAGE_OR_STATUS",
        ),
        (
            lambda d: d["cross_platform_comparison"].update(copied_source=True),
            "CROSS_PLATFORM_COPY_OR_TAMPER",
        ),
        (lambda d: d["gates"].update(writes=True), "WRITE_OR_PROMOTION_ATTEMPT"),
        (
            lambda d: d["gates"].update(intent_dna_mutation=True),
            "WRITE_OR_PROMOTION_ATTEMPT",
        ),
        (
            lambda d: d["gates"].update(owned_asset_promotion=True),
            "WRITE_OR_PROMOTION_ATTEMPT",
        ),
    ],
)
def test_metadata_pilot_fails_closed_on_tamper_and_unsafe_scope(mutation, code):
    document = load("SIDEJOB_MARKET")
    mutation(document)
    with pytest.raises(MetadataPilotError, match=code):
        validate_metadata_pilot(encode(document))


def test_manifest_rejects_duplicate_field():
    payload = b'{"schema_version":"a","schema_version":"b"}'
    with pytest.raises(MetadataPilotError, match="DUPLICATE_JSON_FIELD"):
        validate_metadata_pilot(payload)
