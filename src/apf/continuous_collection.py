from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .external_learning import SourceKind


class StartupTrigger(StrEnum):
    OS_BOOT = "OS_BOOT"
    APPLICATION_START = "APPLICATION_START"


class AssetizationBasis(StrEnum):
    NONE = "NONE"
    OWNED = "OWNED"
    EXPLICIT_PERMISSION = "EXPLICIT_PERMISSION"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    CLEAN_ROOM_ABSTRACTION = "CLEAN_ROOM_ABSTRACTION"


class AssetLifecycle(StrEnum):
    REFERENCE_COLLECTED = "REFERENCE_COLLECTED"
    PRINCIPLE_ABSTRACTED = "PRINCIPLE_ABSTRACTED"
    INDEPENDENT_IMPLEMENTATION = "INDEPENDENT_IMPLEMENTATION"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    OWNED_ASSET = "OWNED_ASSET"


@dataclass(frozen=True)
class ContinuousCollectionPolicy:
    enabled: bool = True
    startup_trigger: StartupTrigger = StartupTrigger.OS_BOOT
    collect_immediately: bool = True
    interval_seconds: int = 900
    external_target_ratio: float = 0.65
    internal_target_ratio: float = 0.35
    minimum_intent_relevance: float = 0.30
    max_response_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        if self.interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        if round(self.external_target_ratio + self.internal_target_ratio, 8) != 1:
            raise ValueError("external and internal ratios must total 1")
        if not 0 <= self.minimum_intent_relevance <= 1:
            raise ValueError("minimum_intent_relevance must be between 0 and 1")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")


@dataclass(frozen=True)
class CollectionCandidate:
    source_id: str
    kind: SourceKind
    locator: str
    intent_relevance: float
    content_hash_seen: bool = False
    explicitly_authorized: bool = False
    contains_personal_data: bool = False
    contains_secrets: bool = False
    requires_credentials: bool = False
    robots_allowed: bool = True
    terms_allowed: bool = True
    license_clarity: float = 0.0
    assetization_basis: AssetizationBasis = AssetizationBasis.NONE
    provenance_recorded: bool = False
    copied_source_code: bool = False
    rights_review_passed: bool = False
    owner_approval_digest: str | None = None
    independent_implementation: bool = False
    original_expression_excluded: bool = False
    distinctive_category_count: int = 0
    functional_distinction: bool = False
    similarity_review_passed: bool = False


@dataclass(frozen=True)
class CollectionDecision:
    collect: bool
    reusable: bool
    reason: str


@dataclass(frozen=True)
class AssetizationRoute:
    current: AssetLifecycle
    next_step: AssetLifecycle | None
    may_publish_as_owned: bool


@dataclass(frozen=True)
class StartupPlan:
    start_on_boot: bool
    first_collection_delay_seconds: int
    repeat_interval_seconds: int


def startup_plan(policy: ContinuousCollectionPolicy) -> StartupPlan:
    return StartupPlan(
        start_on_boot=policy.enabled and policy.startup_trigger == StartupTrigger.OS_BOOT,
        first_collection_delay_seconds=0 if policy.enabled and policy.collect_immediately else policy.interval_seconds,
        repeat_interval_seconds=policy.interval_seconds,
    )


def decide_collection(
    candidate: CollectionCandidate,
    policy: ContinuousCollectionPolicy,
) -> CollectionDecision:
    if not policy.enabled:
        return CollectionDecision(False, False, "COLLECTION_DISABLED")
    if candidate.content_hash_seen:
        return CollectionDecision(False, False, "DUPLICATE_CONTENT")
    if candidate.intent_relevance < policy.minimum_intent_relevance:
        return CollectionDecision(False, False, "LOW_INTENT_RELEVANCE")
    if candidate.contains_personal_data:
        return CollectionDecision(False, False, "PERSONAL_DATA_BLOCKED")
    if candidate.contains_secrets:
        return CollectionDecision(False, False, "SECRET_CONTENT_BLOCKED")
    if candidate.requires_credentials:
        return CollectionDecision(False, False, "CREDENTIAL_ACCESS_BLOCKED")
    if not candidate.robots_allowed or not candidate.terms_allowed:
        return CollectionDecision(False, False, "SOURCE_POLICY_BLOCKED")
    if candidate.kind in {SourceKind.OWNED, SourceKind.CLIENT_DELEGATED} and not candidate.explicitly_authorized:
        return CollectionDecision(False, False, "EXPLICIT_AUTHORIZATION_REQUIRED")
    licensed_reuse = candidate.license_clarity >= 0.80
    base_assetization = (
        candidate.assetization_basis
        in {
            AssetizationBasis.OWNED,
            AssetizationBasis.EXPLICIT_PERMISSION,
            AssetizationBasis.PUBLIC_DOMAIN,
        }
        and candidate.provenance_recorded
        and not candidate.copied_source_code
    )
    clean_room_exception = (
        candidate.assetization_basis == AssetizationBasis.CLEAN_ROOM_ABSTRACTION
        and candidate.provenance_recorded
        and not candidate.copied_source_code
        and candidate.rights_review_passed
        and isinstance(candidate.owner_approval_digest, str)
        and len(candidate.owner_approval_digest) == 71
        and candidate.owner_approval_digest.startswith("sha256:")
        and candidate.independent_implementation
        and candidate.original_expression_excluded
        and candidate.distinctive_category_count >= 2
        and candidate.functional_distinction
        and candidate.similarity_review_passed
    )
    independent_assetization = base_assetization or clean_room_exception
    reusable = licensed_reuse or independent_assetization
    if independent_assetization and not licensed_reuse:
        return CollectionDecision(True, True, "COLLECT_INDEPENDENT_ASSET")
    return CollectionDecision(
        True,
        reusable,
        "COLLECT_REFERENCE_FOR_INDEPENDENT_DEVELOPMENT" if not reusable else "COLLECT_REUSABLE",
    )


def assetization_route(stage: AssetLifecycle) -> AssetizationRoute:
    sequence = (
        AssetLifecycle.REFERENCE_COLLECTED,
        AssetLifecycle.PRINCIPLE_ABSTRACTED,
        AssetLifecycle.INDEPENDENT_IMPLEMENTATION,
        AssetLifecycle.INDEPENDENTLY_VERIFIED,
        AssetLifecycle.OWNED_ASSET,
    )
    index = sequence.index(stage)
    next_step = sequence[index + 1] if index + 1 < len(sequence) else None
    return AssetizationRoute(stage, next_step, stage == AssetLifecycle.OWNED_ASSET)
