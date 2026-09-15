from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

SCHEMA_VERSION = "apf.owned-platform-readonly-manifest/v1"
_SHA1 = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_SAFE_PATH = re.compile(r"\A[A-Za-z0-9_.\-/]+\Z")
_FORBIDDEN_KEYS = frozenset(
    {
        "content",
        "source_code",
        "raw",
        "customer_data",
        "secret",
        "credential",
        "internal_price",
        "pricing",
    }
)


class PilotManifestError(ValueError):
    pass


class CandidateStatus(StrEnum):
    CANDIDATE = "CANDIDATE"


class ReviewStatus(StrEnum):
    ETHERNIAN_REVIEW_REQUIRED = "ETHERNIAN_REVIEW_REQUIRED"


@dataclass(frozen=True)
class PilotValidationResult:
    schema_version: str
    source_repository: str
    source_commit: str
    evidence_count: int
    candidate_names: tuple[str, ...]
    role_flow: tuple[str, ...]
    mutation_allowed: bool
    promotion_allowed: bool


def canonical_source_identity(
    *, repository: str, commit: str, path: str, blob_sha1: str
) -> str:
    return f"github:{repository}@{commit}:{path}#blob:{blob_sha1}"


def evidence_ref_for_identity(identity: str) -> str:
    return "sha256:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PilotManifestError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _require_exact_keys(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PilotManifestError(code)
    return value


def _walk_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in _FORBIDDEN_KEYS:
                raise PilotManifestError("PROHIBITED_PAYLOAD_FIELD")
            _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            _walk_keys(child)


def validate_readonly_manifest(payload: bytes) -> PilotValidationResult:
    try:
        document = json.loads(payload, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PilotManifestError("INVALID_JSON") from exc
    root = _require_exact_keys(
        document,
        {
            "schema_version",
            "pilot_id",
            "source",
            "authorization",
            "boundaries",
            "evidence",
            "candidates",
            "role_flow",
        },
        "INVALID_MANIFEST_SCHEMA",
    )
    _walk_keys(root)
    source = _require_exact_keys(
        root["source"], {"repository", "ref", "commit", "tree_sha1"}, "INVALID_SOURCE_SCHEMA"
    )
    auth = _require_exact_keys(
        root["authorization"],
        {"relationship", "basis", "license_scope", "provenance_policy"},
        "INVALID_AUTHORIZATION_SCHEMA",
    )
    boundaries = _require_exact_keys(
        root["boundaries"],
        {
            "read_only_source",
            "copy_source_material",
            "mutate_intent_dna",
            "promote_owned_asset",
            "sensitive_value_policy",
        },
        "INVALID_BOUNDARY_SCHEMA",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise PilotManifestError("UNSUPPORTED_SCHEMA_VERSION")
    if (
        source["repository"] != "NurionHoldings/mjn"
        or source["ref"] != "main"
        or not isinstance(source["commit"], str)
        or _SHA1.fullmatch(source["commit"]) is None
        or not isinstance(source["tree_sha1"], str)
        or _SHA1.fullmatch(source["tree_sha1"]) is None
    ):
        raise PilotManifestError("INVALID_CANONICAL_SOURCE")
    if (
        auth["relationship"] != "FIRST_PARTY"
        or auth["basis"] != "OWNER_AUTHORIZED_ANALYSIS"
        or auth["license_scope"] != "ANALYSIS_ONLY_NO_CODE_REPUBLICATION"
        or auth["provenance_policy"] != "CANONICAL_IDENTITY_AND_SHA256_ONLY"
    ):
        raise PilotManifestError("AUTHORIZATION_NOT_PROVEN")
    if boundaries != {
        "read_only_source": True,
        "copy_source_material": False,
        "mutate_intent_dna": False,
        "promote_owned_asset": False,
        "sensitive_value_policy": "REPORT_VIOLATION_CODE_ONLY",
    }:
        raise PilotManifestError("CLEAN_ROOM_BOUNDARY_VIOLATION")

    evidence = root["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise PilotManifestError("EVIDENCE_REQUIRED")
    seen: set[str] = set()
    for item_value in evidence:
        item = _require_exact_keys(
            item_value,
            {"path", "blob_sha1", "canonical_identity", "evidence_ref", "kind"},
            "INVALID_EVIDENCE_SCHEMA",
        )
        path = item["path"]
        if (
            not isinstance(path, str)
            or _SAFE_PATH.fullmatch(path) is None
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or not isinstance(item["blob_sha1"], str)
            or _SHA1.fullmatch(item["blob_sha1"]) is None
            or item["kind"] not in {"CODE", "TEST", "DOCUMENT", "SCHEMA"}
        ):
            raise PilotManifestError("INVALID_EVIDENCE_IDENTITY")
        identity = canonical_source_identity(
            repository=source["repository"],
            commit=source["commit"],
            path=path,
            blob_sha1=item["blob_sha1"],
        )
        if item["canonical_identity"] != identity:
            raise PilotManifestError("CANONICAL_IDENTITY_MISMATCH")
        if not isinstance(item["evidence_ref"], str) or _SHA256.fullmatch(
            item["evidence_ref"]
        ) is None:
            raise PilotManifestError("INVALID_EVIDENCE_REF")
        if item["evidence_ref"] != evidence_ref_for_identity(identity):
            raise PilotManifestError("EVIDENCE_REF_MISMATCH")
        if identity in seen:
            raise PilotManifestError("DUPLICATE_EVIDENCE")
        seen.add(identity)

    candidates = root["candidates"]
    if not isinstance(candidates, list) or len(candidates) < 3:
        raise PilotManifestError("MINIMUM_CANDIDATES_REQUIRED")
    names: list[str] = []
    for candidate_value in candidates:
        candidate = _require_exact_keys(
            candidate_value,
            {
                "name",
                "status",
                "review_status",
                "abstract_spec",
                "evidence_refs",
                "owned_asset",
            },
            "INVALID_CANDIDATE_SCHEMA",
        )
        refs = candidate["evidence_refs"]
        if (
            not isinstance(candidate["name"], str)
            or not candidate["name"]
            or candidate["status"] != CandidateStatus.CANDIDATE.value
            or candidate["review_status"] != ReviewStatus.ETHERNIAN_REVIEW_REQUIRED.value
            or candidate["owned_asset"] is not False
            or not isinstance(candidate["abstract_spec"], dict)
            or not isinstance(refs, list)
            or not refs
            or any(ref not in {item["evidence_ref"] for item in evidence} for ref in refs)
        ):
            raise PilotManifestError("UNSAFE_CANDIDATE")
        names.append(candidate["name"])
    if len(names) != len(set(names)):
        raise PilotManifestError("DUPLICATE_CANDIDATE")

    role_flow = root["role_flow"]
    expected_flow = ["RESEARCH", "ANALYZE", "ARCHITECT", "BUILD", "TEST", "AUDIT"]
    if role_flow != expected_flow:
        raise PilotManifestError("INVALID_ROLE_FLOW")
    return PilotValidationResult(
        schema_version=SCHEMA_VERSION,
        source_repository=source["repository"],
        source_commit=source["commit"],
        evidence_count=len(evidence),
        candidate_names=tuple(names),
        role_flow=tuple(role_flow),
        mutation_allowed=False,
        promotion_allowed=False,
    )
