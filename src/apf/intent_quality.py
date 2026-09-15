from __future__ import annotations

from dataclasses import dataclass

from .domain import CRITICAL_AXES, INTENT_AXES, IntentDNA


@dataclass(frozen=True)
class IntentQuality:
    completeness: float
    consistency: float
    clarity: float
    authority_precision: float
    evidence_quality: float
    testability: float
    score: float
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True)
class IntentTrace:
    intent_axis: str
    implementation_refs: tuple[str, ...] = ()
    test_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntentCoverage:
    implementation: float
    tests: float
    evidence: float
    end_to_end: float
    uncovered_axes: tuple[str, ...]


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def score_intent(dna: IntentDNA) -> IntentQuality:
    statements = [statement for values in dna.axes.values() for statement in values]
    present = {axis for axis in INTENT_AXES if dna.axes.get(axis)}
    critical_missing = sorted(CRITICAL_AXES - present)
    disputed = sum(statement.disputed for statement in statements)
    vague = sum(len(statement.canonical_text.split()) < 3 for statement in statements)

    completeness = _ratio(len(present), len(INTENT_AXES))
    consistency = 1.0 - _ratio(disputed, len(statements)) if statements else 0.0
    clarity = 1.0 - _ratio(vague, len(statements)) if statements else 0.0
    authority_precision = 1.0 if dna.axes.get("owner") and dna.axes.get("constraint") else 0.0
    evidence_quality = (
        round(sum(statement.confidence for statement in statements) / len(statements), 4)
        if statements
        else 0.0
    )
    testability = 1.0 if dna.axes.get("outcome") and dna.axes.get("signal") else 0.0
    score = round(
        completeness * 0.25
        + consistency * 0.15
        + clarity * 0.10
        + authority_precision * 0.20
        + evidence_quality * 0.15
        + testability * 0.15,
        4,
    )
    blockers = []
    if critical_missing:
        blockers.append("CRITICAL_AXES_MISSING:" + ",".join(critical_missing))
    if disputed:
        blockers.append("DISPUTED_INTENT")
    if authority_precision < 1:
        blockers.append("AUTHORITY_IMPRECISE")
    if testability < 1:
        blockers.append("OUTCOME_NOT_TESTABLE")
    if evidence_quality < 0.80:
        blockers.append("EVIDENCE_QUALITY_LOW")
    return IntentQuality(
        completeness=completeness,
        consistency=consistency,
        clarity=clarity,
        authority_precision=authority_precision,
        evidence_quality=evidence_quality,
        testability=testability,
        score=score,
        blocking_reasons=tuple(blockers),
    )


def measure_coverage(traces: list[IntentTrace]) -> IntentCoverage:
    by_axis = {trace.intent_axis: trace for trace in traces if trace.intent_axis in INTENT_AXES}
    implementation = _ratio(sum(bool(t.implementation_refs) for t in by_axis.values()), len(INTENT_AXES))
    tests = _ratio(sum(bool(t.test_refs) for t in by_axis.values()), len(INTENT_AXES))
    evidence = _ratio(sum(bool(t.evidence_refs) for t in by_axis.values()), len(INTENT_AXES))
    end_to_end = _ratio(
        sum(bool(t.implementation_refs and t.test_refs and t.evidence_refs) for t in by_axis.values()),
        len(INTENT_AXES),
    )
    uncovered = tuple(axis for axis in INTENT_AXES if axis not in by_axis or not all(
        (by_axis[axis].implementation_refs, by_axis[axis].test_refs, by_axis[axis].evidence_refs)
    ))
    return IntentCoverage(implementation, tests, evidence, end_to_end, uncovered)


def can_lock_intent(quality: IntentQuality, *, minimum_score: float = 0.85) -> bool:
    """Quality may permit review, but only a human approval can perform the lock."""
    return quality.score >= minimum_score and not quality.blocking_reasons
