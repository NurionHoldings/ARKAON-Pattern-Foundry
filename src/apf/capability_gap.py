"""Detect capability gaps: external platforms have X, owned platform does not — then request actions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .evolution_domains import EvolutionDomainRejected, default_catalog
from .experience_audit_bridge import collect_openapi_paths, collect_policy_route_refs

_FORBIDDEN_TOKEN = re.compile(r"(secret|credential|password|token|pii|member|order)", re.IGNORECASE)


class CapabilityGapRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GapSeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ActionKind(str, Enum):
    ETERNIAN_REVIEW = "ETERNIAN_REVIEW"
    RESEARCH = "RESEARCH"
    OPERATOR_DECISION = "OPERATOR_DECISION"


@dataclass(frozen=True)
class CapabilityGapPolicy:
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False
    emit_eternian_packet: bool = True
    emit_research_packet: bool = True
    minimum_external_references: int = 1
    minimum_gaps_for_packet: int = 1
    max_gaps_per_report: int = 20

    @classmethod
    def load(cls, path: Path) -> CapabilityGapPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-capability-gap/v1":
            raise CapabilityGapRejected("POLICY_SCHEMA", "unsupported capability gap schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise CapabilityGapRejected("POLICY_FORBIDDEN", "capability gap must remain request-only")
        return cls(
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            emit_eternian_packet=bool(document.get("emit_eternian_packet", True)),
            emit_research_packet=bool(document.get("emit_research_packet", True)),
            minimum_external_references=max(1, int(document.get("minimum_external_references", 1))),
            minimum_gaps_for_packet=max(1, int(document.get("minimum_gaps_for_packet", 1))),
            max_gaps_per_report=max(1, int(document.get("max_gaps_per_report", 20))),
        )


@dataclass(frozen=True)
class CapabilityInventory:
    platform_id: str
    source: str
    tokens: frozenset[str]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class RequestedAction:
    action_id: str
    kind: ActionKind
    summary: str
    inbox_stage: str

    def to_document(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "kind": self.kind.value,
            "summary": self.summary,
            "inbox_stage": self.inbox_stage,
        }


@dataclass(frozen=True)
class CapabilityGap:
    gap_id: str
    owned_platform_id: str
    capability_token: str
    capability_label: str
    external_platform_ids: tuple[str, ...]
    severity: GapSeverity
    user_message: str
    evidence_refs: tuple[str, ...]
    requested_actions: tuple[RequestedAction, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "gap_id": self.gap_id,
            "owned_platform_id": self.owned_platform_id,
            "capability_token": self.capability_token,
            "capability_label": self.capability_label,
            "external_platform_ids": list(self.external_platform_ids),
            "severity": self.severity.value,
            "user_message": self.user_message,
            "evidence_refs": list(self.evidence_refs),
            "requested_actions": [item.to_document() for item in self.requested_actions],
        }


@dataclass(frozen=True)
class CapabilityGapReport:
    foundry_root: Path
    evaluated_at: datetime
    owned_platform_id: str
    gaps: tuple[CapabilityGap, ...]
    owned_token_count: int
    external_token_count: int
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.capability-gap-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "owned_platform_id": self.owned_platform_id,
            "owned_token_count": self.owned_token_count,
            "external_token_count": self.external_token_count,
            "gap_count": len(self.gaps),
            "report_digest": self.report_digest,
            "gaps": [item.to_document() for item in self.gaps],
        }


def _tokenize_openapi_path(path: str) -> str | None:
    parts = [part for part in path.strip("/").split("/") if part and not part.startswith("{")]
    if not parts:
        return "api-surface:root"
    leaf = parts[-1].casefold()
    if _FORBIDDEN_TOKEN.search(leaf):
        return None
    return f"api-surface:{leaf}"


def _tokenize_policy_route(route: str) -> str | None:
    cleaned = route.strip("/").casefold()
    if not cleaned or _FORBIDDEN_TOKEN.search(cleaned):
        return None
    return f"policy-route:{cleaned.replace('/', '-')}"


def _label_for_token(token: str) -> str:
    prefix, _, tail = token.partition(":")
    labels = {
        "api-surface": f"API surface '{tail}'",
        "policy-route": f"policy-bound route '{tail}'",
        "landing-pattern": f"landing pattern '{tail}'",
        "ui-route": f"UI route ref '{tail}'",
        "fetch-pattern": f"client fetch pattern '{tail}'",
        "ux-type": f"typography capability '{tail}'",
        "ux-color": f"color system capability '{tail}'",
        "ux-motion": f"motion capability '{tail}'",
        "ux-template": f"template capability '{tail}'",
        "ux-home": f"home surface capability '{tail}'",
        "ux-auth": f"auth/onboarding capability '{tail}'",
        "ux-video": f"video template capability '{tail}'",
        "ux-coherence": f"cross-feature capability '{tail}'",
        "ux-pay": f"payment/checkout capability '{tail}'",
        "ux-lifecycle": f"lifecycle stewardship capability '{tail}'",
        "market-watch": f"emerging market capability '{tail}'",
    }
    return labels.get(prefix, token)


def _load_landing_intent_tokens(foundry_root: Path, platform_id: str) -> frozenset[str]:
    directory = foundry_root / "knowledge" / "landing-intents"
    if not directory.is_dir():
        return frozenset()
    for path in directory.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        platform = document.get("platform") or {}
        if platform.get("id") != platform_id:
            continue
        focus = document.get("learning_focus") or {}
        patterns = focus.get("priority_patterns") or ()
        return frozenset(f"landing-pattern:{item}" for item in patterns if isinstance(item, str))
    return frozenset()


def _inventory_from_surface(document: dict[str, object], *, ref: str) -> frozenset[str]:
    tokens: set[str] = set()
    for path in document.get("openapi_paths") or ():
        if isinstance(path, str):
            token = _tokenize_openapi_path(path)
            if token:
                tokens.add(token)
    for route in document.get("policy_route_refs") or ():
        if isinstance(route, str):
            token = _tokenize_policy_route(route)
            if token:
                tokens.add(token)
    for item in document.get("js_structures") or ():
        if not isinstance(item, dict):
            continue
        for route in item.get("route_refs") or ():
            if isinstance(route, str) and not _FORBIDDEN_TOKEN.search(route):
                tokens.add(f"ui-route:{route.casefold()}")
        for pattern in item.get("fetch_patterns") or ():
            if isinstance(pattern, str) and not _FORBIDDEN_TOKEN.search(pattern):
                digest = sha256(pattern.encode()).hexdigest()[:12]
                tokens.add(f"fetch-pattern:{digest}")
    del ref
    return frozenset(tokens)


def build_platform_inventory(
    *,
    foundry_root: Path,
    platform_id: str,
    platform_path: Path | None = None,
    source: str,
) -> CapabilityInventory:
    tokens: set[str] = set()
    evidence: list[str] = []
    if platform_path is not None and platform_path.is_dir():
        for path in collect_openapi_paths(platform_path):
            token = _tokenize_openapi_path(path)
            if token:
                tokens.add(token)
        for route in collect_policy_route_refs(platform_path):
            token = _tokenize_policy_route(route)
            if token:
                tokens.add(token)
        evidence.append(platform_path.as_posix())
    tokens.update(_load_landing_intent_tokens(foundry_root, platform_id))
    store = foundry_root / "state" / "surface-observations"
    if store.is_dir():
        for path in store.glob("*.json"):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if document.get("platform_id") != platform_id:
                continue
            tokens.update(_inventory_from_surface(document, ref=path.as_posix()))
            evidence.append(path.relative_to(foundry_root).as_posix())
    return CapabilityInventory(platform_id, source, frozenset(tokens), tuple(sorted(set(evidence))))


def collect_external_inventories(foundry_root: Path, *, exclude_platform_id: str) -> dict[str, CapabilityInventory]:
    inventories: dict[str, CapabilityInventory] = {}
    store = foundry_root / "state" / "surface-observations"
    if store.is_dir():
        for path in sorted(store.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            platform_id = str(document.get("platform_id", "UNKNOWN"))
            if platform_id == exclude_platform_id:
                continue
            tokens = _inventory_from_surface(document, ref=path.as_posix())
            landing = _load_landing_intent_tokens(foundry_root, platform_id)
            merged = frozenset(set(tokens) | set(landing))
            if not merged:
                continue
            ref = path.relative_to(foundry_root).as_posix()
            prior = inventories.get(platform_id)
            if prior is None:
                inventories[platform_id] = CapabilityInventory(platform_id, "EXTERNAL_SURFACE", merged, (ref,))
            else:
                inventories[platform_id] = CapabilityInventory(
                    platform_id,
                    prior.source,
                    prior.tokens | merged,
                    prior.evidence_refs + (ref,),
                )
    intents = foundry_root / "knowledge" / "landing-intents"
    if intents.is_dir():
        for path in intents.glob("*.json"):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            platform_id = str((document.get("platform") or {}).get("id", ""))
            if not platform_id or platform_id == exclude_platform_id:
                continue
            tokens = _load_landing_intent_tokens(foundry_root, platform_id)
            if not tokens:
                continue
            ref = path.relative_to(foundry_root).as_posix()
            prior = inventories.get(platform_id)
            if prior is None:
                inventories[platform_id] = CapabilityInventory(platform_id, "LANDING_INTENT", tokens, (ref,))
            else:
                inventories[platform_id] = CapabilityInventory(
                    platform_id,
                    prior.source,
                    prior.tokens | tokens,
                    prior.evidence_refs + (ref,),
                )
    return inventories


def _requested_actions(gap_id: str, *, token: str, label: str, owned_platform_id: str) -> tuple[RequestedAction, ...]:
    return (
        RequestedAction(
            f"{gap_id}-research",
            ActionKind.RESEARCH,
            f"{owned_platform_id}: '{label}' 격차에 대한 외부 structural evidence 재확인 및 Intent 정렬",
            "research",
        ),
        RequestedAction(
            f"{gap_id}-eternian",
            ActionKind.ETERNIAN_REVIEW,
            f"{owned_platform_id}: '{label}' ({token}) clean-room 합성·적용 범위 eternian 검토 요청",
            "eternian-review",
        ),
        RequestedAction(
            f"{gap_id}-operator",
            ActionKind.OPERATOR_DECISION,
            f"{owned_platform_id}: '{label}' 격차 해소 우선순위·리소스 operator 배정 요청",
            "operator-decision",
        ),
    )


class CapabilityGapEngine:
    """Core ARKAON loop: external has it, you don't — here are the requested next steps."""

    def __init__(self, *, foundry_root: Path, policy: CapabilityGapPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-capability-gap.json"
        self.policy = policy or CapabilityGapPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "capability-gap"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def analyze_owned_platform(
        self,
        *,
        owned_platform_id: str,
        owned_platform_path: Path | None,
        now: datetime,
    ) -> CapabilityGapReport:
        if now.tzinfo is None:
            raise CapabilityGapRejected("TIMESTAMP", "timezone-aware timestamp required")
        owned = build_platform_inventory(
            foundry_root=self.foundry_root,
            platform_id=owned_platform_id,
            platform_path=owned_platform_path,
            source="OWNED",
        )
        externals = collect_external_inventories(self.foundry_root, exclude_platform_id=owned_platform_id)
        external_union: dict[str, set[str]] = {}
        token_evidence: dict[str, set[str]] = {}
        for inventory in externals.values():
            for token in inventory.tokens:
                external_union.setdefault(token, set()).add(inventory.platform_id)
                token_evidence.setdefault(token, set()).update(inventory.evidence_refs)
        gaps: list[CapabilityGap] = []
        for token, refs in sorted(external_union.items()):
            if len(refs) < self.policy.minimum_external_references:
                continue
            if token in owned.tokens:
                continue
            label = _label_for_token(token)
            refs_sorted = tuple(sorted(refs))
            gap_id = sha256(f"{owned_platform_id}|{token}".encode()).hexdigest()[:16]
            severity = GapSeverity.HIGH if token.startswith("api-surface:") else GapSeverity.MEDIUM
            user_message = (
                f"다른 플랫폼({', '.join(refs_sorted)})에는 {label}이(가) 관측되었으나 "
                f"{owned_platform_id}에는 없습니다. 격차 해소를 위한 조치가 필요합니다."
            )
            gaps.append(
                CapabilityGap(
                    gap_id=gap_id,
                    owned_platform_id=owned_platform_id,
                    capability_token=token,
                    capability_label=label,
                    external_platform_ids=refs_sorted,
                    severity=severity,
                    user_message=user_message,
                    evidence_refs=tuple(sorted(token_evidence.get(token, ()))),
                    requested_actions=_requested_actions(
                        gap_id, token=token, label=label, owned_platform_id=owned_platform_id
                    ),
                )
            )
        try:
            catalog = default_catalog(self.foundry_root)
        except EvolutionDomainRejected:
            catalog = None
        if catalog is not None:
            config_ref = catalog.config_path.relative_to(self.foundry_root).as_posix()
            for token in sorted(catalog.all_capability_tokens):
                if token in owned.tokens:
                    continue
                if any(item.capability_token == token for item in gaps):
                    continue
                label = _label_for_token(token)
                gap_id = sha256(f"{owned_platform_id}|evolution|{token}".encode()).hexdigest()[:16]
                user_message = (
                    f"{owned_platform_id}의 진화 학습 커리큘럼에 {label}이(가) 아직 축적·적용되지 않았습니다. "
                    "외부 structural 관측과 reflective lesson 축적이 필요합니다."
                )
                gaps.append(
                    CapabilityGap(
                        gap_id=gap_id,
                        owned_platform_id=owned_platform_id,
                        capability_token=token,
                        capability_label=label,
                        external_platform_ids=("EVOLUTION_CURRICULUM",),
                        severity=GapSeverity.LOW,
                        user_message=user_message,
                        evidence_refs=(config_ref,),
                        requested_actions=_requested_actions(
                            gap_id, token=token, label=label, owned_platform_id=owned_platform_id
                        ),
                    )
                )
        gaps.sort(
            key=lambda item: (
                {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[item.severity.value],
                -len(item.external_platform_ids),
                item.capability_token,
            )
        )
        limited = tuple(gaps[: self.policy.max_gaps_per_report])
        document = {
            "evaluated_at": now.isoformat(),
            "owned_platform_id": owned_platform_id,
            "gap_count": len(limited),
        }
        digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        return CapabilityGapReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            owned_platform_id=owned_platform_id,
            gaps=limited,
            owned_token_count=len(owned.tokens),
            external_token_count=len(external_union),
            report_digest=digest,
        )

    def persist(self, report: CapabilityGapReport) -> Path:
        target = self.store_root / (
            f"{report.evaluated_at.strftime('%Y-%m-%d')}-{report.owned_platform_id}-{report.report_digest[:12]}.json"
        )
        target.write_text(
            json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target
