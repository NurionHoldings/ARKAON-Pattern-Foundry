from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Precedent:
    source_id: str
    feature: str
    authority: float
    production_maturity: float
    failure_coverage: float
    interoperability: float
    intent_relevance: float
    provenance_recorded: bool
    independent_source_group: str


@dataclass(frozen=True)
class PrecedentAssessment:
    source_id: str
    score: float
    qualified: bool
    extract: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkPlan:
    assessments: tuple[PrecedentAssessment, ...]
    covered_features: tuple[str, ...]
    uncovered_features: tuple[str, ...]
    ready_for_independent_design: bool


@dataclass(frozen=True)
class EthernianAssistanceRequest:
    feature: str
    blockage_reason: str
    requested_help: tuple[str, ...]
    prohibited_help: tuple[str, ...]
    status: str


def assess_precedent(value: Precedent, *, threshold: float = 0.70) -> PrecedentAssessment:
    score = round(
        value.authority * 0.20
        + value.production_maturity * 0.25
        + value.failure_coverage * 0.20
        + value.interoperability * 0.15
        + value.intent_relevance * 0.20,
        4,
    )
    qualified = value.provenance_recorded and score >= threshold and value.intent_relevance >= 0.50
    return PrecedentAssessment(
        source_id=value.source_id,
        score=score,
        qualified=qualified,
        extract=("FUNCTION", "INTERFACE", "FAILURE_MODE", "RECOVERY", "ACCEPTANCE_CRITERIA"),
    )


def build_benchmark_plan(
    required_features: set[str],
    precedents: list[Precedent],
) -> BenchmarkPlan:
    assessed = [(item, assess_precedent(item)) for item in precedents]
    qualified = [(item, result) for item, result in assessed if result.qualified]
    covered = tuple(sorted(required_features & {item.feature for item, _ in qualified}))
    uncovered = tuple(sorted(required_features - set(covered)))
    results = tuple(result for _, result in sorted(qualified, key=lambda row: (-row[1].score, row[0].source_id)))
    return BenchmarkPlan(results, covered, uncovered, not uncovered)


def independent_groups_for_feature(feature: str, precedents: list[Precedent]) -> int:
    return len(
        {
            item.independent_source_group
            for item in precedents
            if item.feature == feature and assess_precedent(item).qualified
        }
    )


def request_ethernian_assistance(feature: str, blockage_reason: str) -> EthernianAssistanceRequest:
    """Escalate a blocked precedent without asking for restricted copying or access bypass."""
    if not feature.strip() or not blockage_reason.strip():
        raise ValueError("feature and blockage_reason are required")
    return EthernianAssistanceRequest(
        feature=feature,
        blockage_reason=blockage_reason,
        requested_help=(
            "FIND_ALTERNATIVE_PRECEDENTS",
            "ABSTRACT_FUNCTIONAL_PRINCIPLES",
            "DRAFT_CLEAN_ROOM_SPECIFICATION",
            "DESIGN_INDEPENDENT_ACCEPTANCE_TESTS",
            "CHECK_INTENT_DNA_ALIGNMENT",
        ),
        prohibited_help=(
            "COPY_RESTRICTED_SOURCE",
            "BYPASS_ACCESS_CONTROL",
            "REMOVE_LICENSE_NOTICE",
            "RECONSTRUCT_PROPRIETARY_EXPRESSION",
        ),
        status="AWAITING_ETHERNIAN_ASSISTANCE",
    )
