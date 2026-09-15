from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "apf.clean-room-analog-synthesis/v1"
EXPECTED_ROLES = ("RESEARCH", "ANALYZE", "ARCHITECT", "BUILD", "TEST", "AUDIT")
_SHA256 = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"\A[a-z0-9][a-z0-9_.-]{2,79}\Z")
_PROHIBITED_KEYS = frozenset(
    {"quote", "quoted_text", "raw_content", "source_code", "secret", "credential", "pii"}
)


class AnalogSynthesisError(ValueError):
    pass


@dataclass(frozen=True)
class AnalogSynthesisResult:
    campaign_id: str
    source_families: tuple[str, ...]
    source_lineages: tuple[str, ...]
    candidate_names: tuple[str, ...]
    role_flow: tuple[str, ...]
    owned_asset: bool = False
    mutation_allowed: bool = False


def opaque_ref(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AnalogSynthesisError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _exact(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise AnalogSynthesisError(code)
    return value


def _walk_boundary(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in _PROHIBITED_KEYS:
                raise AnalogSynthesisError("PROHIBITED_PAYLOAD_FIELD")
            _walk_boundary(child)
    elif isinstance(value, list):
        for child in value:
            _walk_boundary(child)


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for child in value.values() for text in _text_values(child)]
    if isinstance(value, list):
        return [text for child in value for text in _text_values(child)]
    return []


def _check_leakage(generated: dict[str, Any], forbidden: list[str]) -> None:
    normalized = " ".join(_text_values(generated)).casefold()
    if "http://" in normalized or "https://" in normalized:
        raise AnalogSynthesisError("SOURCE_URL_LEAKAGE")
    for token in forbidden:
        if not isinstance(token, str) or len(token) < 4:
            raise AnalogSynthesisError("INVALID_LEAKAGE_GUARD")
        if token.casefold() in normalized:
            raise AnalogSynthesisError("SOURCE_IDENTIFIER_LEAKAGE")


def validate_analog_manifest(payload: bytes) -> AnalogSynthesisResult:
    try:
        document = json.loads(payload, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AnalogSynthesisError("INVALID_JSON") from exc
    root = _exact(
        document,
        {
            "schema_version",
            "campaign_id",
            "retrieved_at",
            "boundaries",
            "sources",
            "mjn_input",
            "candidates",
            "role_flow",
            "leakage_guard",
        },
        "INVALID_MANIFEST_SCHEMA",
    )
    _walk_boundary(root)
    if root["schema_version"] != SCHEMA_VERSION:
        raise AnalogSynthesisError("UNSUPPORTED_SCHEMA_VERSION")
    if not isinstance(root["campaign_id"], str) or _SAFE_ID.fullmatch(root["campaign_id"]) is None:
        raise AnalogSynthesisError("INVALID_CAMPAIGN_ID")
    try:
        retrieved = datetime.fromisoformat(root["retrieved_at"])
    except (AttributeError, ValueError) as exc:
        raise AnalogSynthesisError("INVALID_RETRIEVAL_TIME") from exc
    if retrieved.tzinfo is None:
        raise AnalogSynthesisError("INVALID_RETRIEVAL_TIME")

    boundaries = _exact(
        root["boundaries"],
        {
            "mjn_read_only",
            "copy_external_material",
            "store_quoted_text",
            "mutate_intent_dna",
            "promote_owned_asset",
            "sensitive_data",
        },
        "INVALID_BOUNDARY_SCHEMA",
    )
    if boundaries != {
        "mjn_read_only": True,
        "copy_external_material": False,
        "store_quoted_text": False,
        "mutate_intent_dna": False,
        "promote_owned_asset": False,
        "sensitive_data": "REJECT_PII_SECRET_CUSTOMER_DATA",
    }:
        raise AnalogSynthesisError("CLEAN_ROOM_BOUNDARY_VIOLATION")

    sources = root["sources"]
    if not isinstance(sources, list) or len(sources) < 3:
        raise AnalogSynthesisError("THREE_SOURCE_FAMILIES_REQUIRED")
    source_by_ref: dict[str, dict[str, Any]] = {}
    families: set[str] = set()
    lineages: set[str] = set()
    for raw_source in sources:
        source = _exact(
            raw_source,
            {
                "family",
                "lineage",
                "official_url",
                "canonical_identity_ref",
                "retrieved_at",
                "content_digest",
                "evidence_ref",
                "authority",
                "access_posture",
                "license_terms_posture",
            },
            "INVALID_SOURCE_SCHEMA",
        )
        if (
            not isinstance(source["family"], str)
            or _SAFE_ID.fullmatch(source["family"]) is None
            or not isinstance(source["lineage"], str)
            or _SAFE_ID.fullmatch(source["lineage"]) is None
            or source["authority"] != "OFFICIAL_FIRST_PARTY"
            or source["access_posture"] != "PUBLIC_DOCS_MANUAL_RETRIEVAL"
            or source["retrieved_at"] != root["retrieved_at"]
            or source["license_terms_posture"]
            not in {"REFERENCE_ONLY_NO_REPUBLICATION", "OPEN_LICENSE_REFERENCE_ONLY"}
            or not isinstance(source["official_url"], str)
            or not source["official_url"].startswith("https://")
            or not all(
                isinstance(source[field], str) and _SHA256.fullmatch(source[field])
                for field in ("canonical_identity_ref", "content_digest", "evidence_ref")
            )
        ):
            raise AnalogSynthesisError("UNTRUSTED_SOURCE")
        if source["canonical_identity_ref"] != opaque_ref(source["official_url"]):
            raise AnalogSynthesisError("CANONICAL_SOURCE_MISMATCH")
        if source["evidence_ref"] != opaque_ref(
            "|".join(
                (
                    source["canonical_identity_ref"],
                    source["retrieved_at"],
                    source["content_digest"],
                )
            )
        ):
            raise AnalogSynthesisError("SOURCE_EVIDENCE_MISMATCH")
        if source["evidence_ref"] in source_by_ref or source["family"] in families:
            raise AnalogSynthesisError("DUPLICATE_SOURCE")
        source_by_ref[source["evidence_ref"]] = source
        families.add(source["family"])
        lineages.add(source["lineage"])
    if len(lineages) < 3:
        raise AnalogSynthesisError("THREE_SOURCE_FAMILIES_REQUIRED")

    mjn = _exact(
        root["mjn_input"],
        {"manifest_ref", "candidate_names", "first_party_evidence_refs", "write_allowed"},
        "INVALID_MJN_INPUT",
    )
    if (
        not isinstance(mjn["manifest_ref"], str)
        or not _SHA256.fullmatch(mjn["manifest_ref"])
        or mjn["write_allowed"] is not False
        or set(mjn["candidate_names"])
        != {
            "principal-ownership-recheck",
            "transactional-idempotent-transition",
            "financial-sot-audit-chain",
        }
        or not isinstance(mjn["first_party_evidence_refs"], list)
        or not mjn["first_party_evidence_refs"]
        or any(not isinstance(ref, str) or not _SHA256.fullmatch(ref) for ref in mjn["first_party_evidence_refs"])
    ):
        raise AnalogSynthesisError("INVALID_MJN_INPUT")

    guard = _exact(
        root["leakage_guard"], {"mode", "forbidden_identifiers"}, "INVALID_LEAKAGE_GUARD"
    )
    forbidden = guard["forbidden_identifiers"]
    if guard["mode"] != "FAIL_CLOSED" or not isinstance(forbidden, list) or len(forbidden) < 3:
        raise AnalogSynthesisError("INVALID_LEAKAGE_GUARD")

    candidates = root["candidates"]
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise AnalogSynthesisError("THREE_CANDIDATES_REQUIRED")
    names: list[str] = []
    for raw_candidate in candidates:
        candidate = _exact(
            raw_candidate,
            {
                "name",
                "status",
                "review_status",
                "owned_asset",
                "process_steps",
                "invariants",
                "counterexamples",
                "mjn_adaptation",
                "synthetic_tests",
                "external_evidence_refs",
                "mjn_evidence_refs",
            },
            "INVALID_CANDIDATE_SCHEMA",
        )
        ext_refs = candidate["external_evidence_refs"]
        mjn_refs = candidate["mjn_evidence_refs"]
        if (
            candidate["status"] != "ANALOG_SYNTHESIS_CANDIDATE"
            or candidate["review_status"] != "ETHERNIAN_REVIEW_REQUIRED"
            or candidate["owned_asset"] is not False
            or not isinstance(candidate["name"], str)
            or not all(
                isinstance(candidate[field], list) and candidate[field]
                for field in ("process_steps", "invariants", "counterexamples", "synthetic_tests")
            )
            or not isinstance(candidate["mjn_adaptation"], dict)
            or not isinstance(ext_refs, list)
            or any(ref not in source_by_ref for ref in ext_refs)
            or not isinstance(mjn_refs, list)
            or any(ref not in mjn["first_party_evidence_refs"] for ref in mjn_refs)
        ):
            raise AnalogSynthesisError("UNSAFE_CANDIDATE")
        candidate_lineages = {source_by_ref[ref]["lineage"] for ref in ext_refs}
        if len(candidate_lineages) < 2 and not (len(candidate_lineages) == 1 and mjn_refs):
            raise AnalogSynthesisError("SOURCE_DOMINANCE")
        _check_leakage(
            {key: value for key, value in candidate.items() if not key.endswith("evidence_refs")},
            forbidden,
        )
        names.append(candidate["name"])
    if len(names) != len(set(names)):
        raise AnalogSynthesisError("DUPLICATE_CANDIDATE")
    if tuple(root["role_flow"]) != EXPECTED_ROLES:
        raise AnalogSynthesisError("INVALID_ROLE_FLOW")
    return AnalogSynthesisResult(
        campaign_id=root["campaign_id"],
        source_families=tuple(sorted(families)),
        source_lineages=tuple(sorted(lineages)),
        candidate_names=tuple(names),
        role_flow=EXPECTED_ROLES,
    )


class ScopedAuthorityModel:
    """Independent executable model for current-principal, current-scope checks."""

    @staticmethod
    def may_use(*, actor: str, owner: str, active: bool, requested_owner: str) -> bool:
        return active and actor == owner and requested_owner == owner


class OnceTransitionModel:
    """Independent executable model for retry-safe contested transitions."""

    def __init__(self) -> None:
        self._receipts: dict[tuple[str, str], tuple[str, str]] = {}
        self._winner: str | None = None

    def apply(self, *, actor: str, key: str, intent_digest: str) -> str:
        receipt_key = (actor, key)
        previous = self._receipts.get(receipt_key)
        if previous:
            if previous[0] != intent_digest:
                raise AnalogSynthesisError("IDEMPOTENCY_INTENT_CONFLICT")
            return previous[1]
        if self._winner is not None and self._winner != actor:
            raise AnalogSynthesisError("TERMINAL_STATE_CONFLICT")
        self._winner = actor
        receipt = opaque_ref(f"{actor}|{key}|{intent_digest}")
        self._receipts[receipt_key] = (intent_digest, receipt)
        return receipt


class TrustedMoneyModel:
    """Independent executable model for trusted payment facts and immutable settlement."""

    def __init__(self) -> None:
        self._settlements: dict[str, tuple[int, int]] = {}
        self.audit: list[tuple[str, str]] = []

    def settle(
        self,
        *,
        order_id: str,
        actor: str,
        verified_paid_amount: int,
        policy_fee: int,
        client_amount: int | None = None,
        payment_reversed: bool = False,
    ) -> tuple[int, int]:
        del client_amount
        if payment_reversed or verified_paid_amount < 0 or not 0 <= policy_fee <= verified_paid_amount:
            raise AnalogSynthesisError("UNTRUSTED_FINANCIAL_TRANSITION")
        snapshot = (verified_paid_amount, verified_paid_amount - policy_fee)
        previous = self._settlements.setdefault(order_id, snapshot)
        if previous != snapshot:
            raise AnalogSynthesisError("IMMUTABLE_SETTLEMENT_CONFLICT")
        if (actor, order_id) not in self.audit:
            self.audit.append((actor, order_id))
        return previous
