from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "apf.owned-platform-metadata-pilot/v1"


class MetadataPilotError(ValueError):
    pass


class MetadataPilotStatus(StrEnum):
    ETHERNIAN_REVIEW_REQUIRED = "ETHERNIAN_REVIEW_REQUIRED"


@dataclass(frozen=True)
class MetadataPilotResult:
    platform_id: str
    platform_name: str
    candidate_names: tuple[str, ...]
    cross_platform_abstractions: tuple[str, ...]
    status: MetadataPilotStatus
    repository_connection: str
    intent_dna_mutation_allowed: bool = False
    owned_asset_promotion_allowed: bool = False


_PLATFORMS = {
    "NOGADA_NEWS": {
        "pilot_id": "APF-PILOT-041-NOGADA-NEWS",
        "name": "노가다뉴스",
        "authorization_ref": "sha256:1376d8e50d7a429c7b0bd2ba38d35570ff6b0b9f519cd14d69793040ae761a91",
        "surfaces": ("EDITORIAL_WORKFLOW", "SOURCE_PROVENANCE", "PUBLISH_APPROVALS"),
        "workflows": (
            "SOURCE_REGISTER_TO_VERIFICATION",
            "DRAFT_TO_EDITORIAL_REVIEW",
            "APPROVAL_TO_PUBLICATION",
        ),
        "candidates": (
            "source-provenance-ledger",
            "two-stage-publish-approval",
            "correction-aware-editorial-workflow",
        ),
        "cross": ("evidence-bound-approval", "auditable-state-transition"),
    },
    "SIDEJOB_MARKET": {
        "pilot_id": "APF-PILOT-041-SIDEJOB-MARKET",
        "name": "부업장터",
        "authorization_ref": "sha256:c920f470852c9271bbc0614e8e50efed82d97bc6d3724f040ce219f374142dc2",
        "surfaces": (
            "PROVIDER_PARTICIPANT_MATCHING",
            "EARNINGS_OPPORTUNITY_LIFECYCLE",
            "AI_ASSISTANT_DELEGATION",
            "SETTLEMENT_ANTI_FRAUD",
        ),
        "workflows": (
            "OPPORTUNITY_CREATE_TO_MATCH",
            "PARTICIPATION_TO_COMPLETION",
            "DELEGATION_TO_USER_CONFIRMATION",
            "EARNING_VERIFICATION_TO_SETTLEMENT",
        ),
        "candidates": (
            "constraint-aware-opportunity-matching",
            "participant-earnings-lifecycle",
            "bounded-ai-assistant-delegation",
            "evidence-gated-settlement",
        ),
        "cross": (
            "principal-ownership-recheck",
            "transactional-idempotent-transition",
            "financial-sot-audit-chain",
        ),
    },
}

_PROHIBITED = frozenset(
    {
        "PII",
        "SECRET",
        "CREDENTIAL",
        "SESSION",
        "TOKEN",
        "WRITE",
        "INTENT_DNA_MUTATION",
        "OWNED_ASSET_PROMOTION",
    }
)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataPilotError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _exact(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise MetadataPilotError(code)
    return value


def validate_metadata_pilot(payload: bytes) -> MetadataPilotResult:
    try:
        root = json.loads(payload, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MetadataPilotError("INVALID_JSON") from exc
    root = _exact(
        root,
        {
            "schema_version",
            "pilot_id",
            "platform",
            "authorization",
            "collection",
            "domain_metadata",
            "domain_metadata_hash",
            "candidates",
            "cross_platform_comparison",
            "gates",
        },
        "INVALID_MANIFEST_SCHEMA",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise MetadataPilotError("UNSUPPORTED_SCHEMA_VERSION")

    platform = _exact(root["platform"], {"id", "name", "ownership"}, "INVALID_PLATFORM")
    expected = _PLATFORMS.get(platform["id"])
    if expected is None or platform != {
        "id": platform["id"],
        "name": expected["name"],
        "ownership": "FIRST_PARTY_USER_DECLARED",
    }:
        raise MetadataPilotError("WRONG_PLATFORM")
    if root["pilot_id"] != expected["pilot_id"]:
        raise MetadataPilotError("WRONG_PLATFORM")

    auth = _exact(
        root["authorization"],
        {"basis", "evidence_ref", "scope"},
        "INVALID_AUTHORIZATION",
    )
    if auth != {
        "basis": "OWNER_AUTHORIZED_READ_ONLY_METADATA_ANALYSIS",
        "evidence_ref": expected["authorization_ref"],
        "scope": "SUPPLIED_ARCHITECTURE_METADATA_ONLY",
    }:
        raise MetadataPilotError("AUTHORIZATION_NOT_PROVEN")

    collection = _exact(
        root["collection"],
        {"source_basis", "repository_connection", "actual_code_analysis", "allowed_surfaces", "prohibited"},
        "INVALID_COLLECTION_POLICY",
    )
    if (
        collection["source_basis"] != "SUPPLIED_AND_PUBLIC_ARCHITECTURE_METADATA"
        or collection["repository_connection"] != "NOT_RUN_UNAVAILABLE"
        or collection["actual_code_analysis"] is not False
        or tuple(collection["allowed_surfaces"]) != expected["surfaces"]
        or set(collection["prohibited"]) != _PROHIBITED
        or len(collection["prohibited"]) != len(_PROHIBITED)
    ):
        raise MetadataPilotError("UNAUTHORIZED_SURFACE_OR_OPERATION")

    metadata = root["domain_metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {"workflows", "source_claim"}:
        raise MetadataPilotError("INVALID_DOMAIN_METADATA")
    if (
        tuple(metadata["workflows"]) != expected["workflows"]
        or metadata["source_claim"]
        != "USER_SUPPLIED_CONCEPT_METADATA_NOT_REPOSITORY_OBSERVATION"
        or root["domain_metadata_hash"] != _canonical_hash(metadata)
    ):
        raise MetadataPilotError("FABRICATED_OR_TAMPERED_SOURCE_EVIDENCE")

    candidates = root["candidates"]
    if not isinstance(candidates, list) or len(candidates) != len(expected["candidates"]):
        raise MetadataPilotError("INVALID_CANDIDATES")
    names: list[str] = []
    for item in candidates:
        item = _exact(
            item,
            {"name", "derived_from_workflows", "status", "owned_asset", "contains_source_material"},
            "INVALID_CANDIDATE",
        )
        if (
            item["name"] not in expected["candidates"]
            or item["status"] != MetadataPilotStatus.ETHERNIAN_REVIEW_REQUIRED.value
            or item["owned_asset"] is not False
            or item["contains_source_material"] is not False
            or not isinstance(item["derived_from_workflows"], list)
            or not item["derived_from_workflows"]
            or any(flow not in expected["workflows"] for flow in item["derived_from_workflows"])
        ):
            raise MetadataPilotError("CANDIDATE_LEAKAGE_OR_STATUS")
        names.append(item["name"])
    if tuple(names) != expected["candidates"]:
        raise MetadataPilotError("NONDETERMINISTIC_CANDIDATES")

    comparison = _exact(
        root["cross_platform_comparison"],
        {"reference", "mode", "reusable_abstractions", "copied_source"},
        "INVALID_COMPARISON",
    )
    if comparison != {
        "reference": "MJN-030-ABSTRACT-CANDIDATES",
        "mode": "ABSTRACT_BEHAVIOR_COMPARISON_ONLY",
        "reusable_abstractions": list(expected["cross"]),
        "copied_source": False,
    }:
        raise MetadataPilotError("CROSS_PLATFORM_COPY_OR_TAMPER")

    gates = _exact(
        root["gates"],
        {"intent_dna_mutation", "owned_asset_promotion", "writes", "review_status"},
        "INVALID_GATES",
    )
    if gates != {
        "intent_dna_mutation": False,
        "owned_asset_promotion": False,
        "writes": False,
        "review_status": MetadataPilotStatus.ETHERNIAN_REVIEW_REQUIRED.value,
    }:
        raise MetadataPilotError("WRITE_OR_PROMOTION_ATTEMPT")

    return MetadataPilotResult(
        platform_id=platform["id"],
        platform_name=platform["name"],
        candidate_names=tuple(names),
        cross_platform_abstractions=expected["cross"],
        status=MetadataPilotStatus.ETHERNIAN_REVIEW_REQUIRED,
        repository_connection=collection["repository_connection"],
    )
