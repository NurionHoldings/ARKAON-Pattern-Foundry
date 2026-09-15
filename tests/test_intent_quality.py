from uuid import uuid4

import pytest

from apf.domain import INTENT_AXES, IntentDNA, IntentStatement
from apf.intent_quality import IntentTrace, can_lock_intent, measure_coverage, score_intent


def statement(text: str = "명확하게 검증 가능한 의도") -> IntentStatement:
    return IntentStatement(
        canonical_text=text,
        evidence_refs=[uuid4()],
        confidence=0.95,
        stability="CORE",
    )


def dna_with(*axes: str) -> IntentDNA:
    return IntentDNA(
        analysis_run_id=uuid4(),
        axes={axis: [statement()] for axis in axes},
        completeness=len(axes) / len(INTENT_AXES),
    )


def test_complete_intent_is_lock_ready_but_not_auto_locked():
    dna = dna_with(*INTENT_AXES)
    quality = score_intent(dna)
    assert quality.score == 1
    assert quality.blocking_reasons == ()
    assert can_lock_intent(quality)
    assert dna.locked is False


def test_missing_authority_and_test_signal_block_lock():
    quality = score_intent(dna_with("why", "who", "outcome", "invariant"))
    assert not can_lock_intent(quality)
    assert "AUTHORITY_IMPRECISE" in quality.blocking_reasons
    assert "OUTCOME_NOT_TESTABLE" in quality.blocking_reasons


def test_coverage_requires_intent_implementation_test_and_evidence_chain():
    complete = IntentTrace("why", ("src/service.py",), ("tests/test_service.py",), ("evidence:1",))
    partial = IntentTrace("who", ("src/auth.py",), (), ("evidence:2",))
    coverage = measure_coverage([complete, partial])
    assert coverage.implementation == pytest.approx(2 / len(INTENT_AXES), abs=0.0001)
    assert coverage.end_to_end == pytest.approx(1 / len(INTENT_AXES), abs=0.0001)
    assert "why" not in coverage.uncovered_axes
    assert "who" in coverage.uncovered_axes


def test_unknown_trace_axes_do_not_inflate_coverage():
    coverage = measure_coverage([IntentTrace("unknown", ("x",), ("y",), ("z",))])
    assert coverage.end_to_end == 0
    assert set(coverage.uncovered_axes) == set(INTENT_AXES)
