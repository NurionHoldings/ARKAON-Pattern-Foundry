from uuid import uuid4

from apf.domain import IntentDNA, IntentStatement
from apf.intent_dna import artifact_should_be_deeply_analyzed, evaluate_gate, fingerprint


def statement(text: str) -> IntentStatement:
    return IntentStatement(canonical_text=text, evidence_refs=[uuid4()], confidence=1, stability="CORE")


def complete_dna() -> IntentDNA:
    axes = {axis: [statement(axis)] for axis in ("why", "who", "outcome", "owner", "invariant", "constraint")}
    return IntentDNA(analysis_run_id=uuid4(), axes=axes, completeness=.9)


def test_complete_dna_passes_gate():
    assert evaluate_gate(complete_dna()).ready


def test_missing_critical_axis_holds():
    dna = complete_dna()
    del dna.axes["owner"]
    assert not evaluate_gate(dna).ready


def test_fingerprint_is_deterministic():
    dna = complete_dna()
    assert fingerprint(dna) == fingerprint(dna)


def test_duplicate_or_low_relevance_skips_deep_analysis():
    assert not artifact_should_be_deeply_analyzed(relevance=.9, content_hash_seen=True, cached_fingerprint_match=False)
    assert not artifact_should_be_deeply_analyzed(relevance=.29, content_hash_seen=False, cached_fingerprint_match=False)
    assert artifact_should_be_deeply_analyzed(relevance=.3, content_hash_seen=False, cached_fingerprint_match=False)

