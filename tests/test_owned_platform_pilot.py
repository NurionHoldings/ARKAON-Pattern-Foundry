import json
from pathlib import Path

import pytest

from apf.owned_platform_pilot import PilotManifestError, validate_readonly_manifest

MANIFEST = Path(__file__).parents[1] / "knowledge" / "pilots" / "mjn-030.json"


def load_document():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def encode(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def test_checked_in_mjn_manifest_is_reproducible_and_read_only():
    result = validate_readonly_manifest(MANIFEST.read_bytes())
    assert result.source_repository == "NurionHoldings/mjn"
    assert result.evidence_count == 15
    assert result.role_flow == (
        "RESEARCH",
        "ANALYZE",
        "ARCHITECT",
        "BUILD",
        "TEST",
        "AUDIT",
    )
    assert result.mutation_allowed is False
    assert result.promotion_allowed is False
    assert set(result.candidate_names) == {
        "principal-ownership-recheck",
        "transactional-idempotent-transition",
        "financial-sot-audit-chain",
    }


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda d: d["boundaries"].update(promote_owned_asset=True), "CLEAN_ROOM"),
        (lambda d: d["candidates"][0].update(owned_asset=True), "UNSAFE_CANDIDATE"),
        (lambda d: d["candidates"][0].update(status="OWNED_ASSET"), "UNSAFE_CANDIDATE"),
        (lambda d: d["candidates"][0].update(review_status="APPROVED"), "UNSAFE_CANDIDATE"),
        (lambda d: d["evidence"][0].update(evidence_ref="sha256:" + "0" * 64), "MISMATCH"),
        (lambda d: d.update(source_code="copied"), "INVALID_MANIFEST_SCHEMA"),
    ],
)
def test_manifest_fails_closed_on_boundary_or_provenance_tampering(mutation, code):
    document = load_document()
    mutation(document)
    with pytest.raises(PilotManifestError, match=code):
        validate_readonly_manifest(encode(document))


def test_candidate_cannot_reference_unregistered_source_evidence():
    document = load_document()
    document["candidates"][0]["evidence_refs"] = ["sha256:" + "1" * 64]
    with pytest.raises(PilotManifestError, match="UNSAFE_CANDIDATE"):
        validate_readonly_manifest(encode(document))
