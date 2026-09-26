"""Execute cross-platform structural learning: fetch, compare, abstract patterns, seed lessons."""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from .analysis_target_resolution import (
    AnalysisTargetResolutionReport,
    CrossPlatformTarget,
    _landing_intent_path,
    _platform_sort_key,
    list_landing_intent_platform_ids,
    load_sought_capability_tokens,
)
from .structural_surface_common import digest_document, structural_signals_from_public_html

_TOKEN_ROUTE_MAP: dict[str, tuple[str, ...]] = {
    "landing-pattern:four-step-process": (
        "flow/step-select",
        "flow/step-info-payment",
        "flow/step-e-contract",
        "flow/step-complete",
    ),
    "landing-pattern:e-contract-flow": ("flow/electronic-contract",),
    "landing-pattern:comparison-table": ("surface/comparison-matrix",),
    "landing-pattern:mypage-dashboard": ("surface/mypage-dashboard",),
    "landing-pattern:hero-single-cta": ("surface/hero-primary-cta",),
    "landing-signal:faq_accordion": ("surface/faq-accordion",),
}


class CrossPlatformLearningRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CrossPlatformLearningPolicy:
    enabled: bool = True
    execute_public_fetch: bool = True
    emit_landing_pattern_proposals: bool = True
    emit_eternian_lesson_packet: bool = True
    max_fetches_per_run: int = 3
    minimum_platforms_for_pattern: int = 2
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False
    platform_urls: frozenset[tuple[str, str]] = frozenset()

    @classmethod
    def load(cls, path: Path) -> CrossPlatformLearningPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.cross-platform-learning/v1":
            raise CrossPlatformLearningRejected("POLICY_SCHEMA", "unsupported cross-platform learning schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise CrossPlatformLearningRejected("POLICY_FORBIDDEN", "cross-platform learning must remain propose-only")
        urls = document.get("platform_urls") or {}
        platform_urls = frozenset(
            (str(platform_id), str(url))
            for platform_id, url in urls.items()
            if isinstance(platform_id, str) and isinstance(url, str) and url.startswith("https://")
        )
        return cls(
            enabled=bool(document.get("enabled", True)),
            execute_public_fetch=bool(document.get("execute_public_fetch", True)),
            emit_landing_pattern_proposals=bool(document.get("emit_landing_pattern_proposals", True)),
            emit_eternian_lesson_packet=bool(document.get("emit_eternian_lesson_packet", True)),
            max_fetches_per_run=max(1, int(document.get("max_fetches_per_run", 3))),
            minimum_platforms_for_pattern=max(2, int(document.get("minimum_platforms_for_pattern", 2))),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            platform_urls=platform_urls,
        )


@dataclass(frozen=True)
class ExecutedObservation:
    platform_id: str
    source_url: str
    observation_path: str
    observation_digest: str
    policy_route_refs: tuple[str, ...]
    skipped_fetch: bool = False
    skip_reason: str = ""

    def to_document(self) -> dict[str, object]:
        return {
            "platform_id": self.platform_id,
            "source_url": self.source_url,
            "observation_path": self.observation_path,
            "observation_digest": self.observation_digest,
            "policy_route_refs": list(self.policy_route_refs),
            "skipped_fetch": self.skipped_fetch,
            "skip_reason": self.skip_reason,
        }


@dataclass(frozen=True)
class LandingStructurePatternProposal:
    pattern_id: str
    pattern_token: str
    platform_ids: tuple[str, ...]
    shared_route_refs: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    summary: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.landing-structure-pattern-proposal/v1",
            "pattern_id": self.pattern_id,
            "pattern_token": self.pattern_token,
            "platform_ids": list(self.platform_ids),
            "shared_route_refs": list(self.shared_route_refs),
            "evidence_digests": list(self.evidence_digests),
            "summary": self.summary,
            "review_status": "PROPOSED",
            "automatic_promotion_allowed": False,
            "production_change_allowed": False,
        }


@dataclass(frozen=True)
class CrossPlatformLessonSeed:
    case_id: str
    pattern_id: str
    platform_scope: str
    principle: str
    reusable_pattern: str
    evidence_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "pattern_id": self.pattern_id,
            "platform_scope": self.platform_scope,
            "principle": self.principle,
            "reusable_pattern": self.reusable_pattern,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True)
class CrossPlatformLearningReport:
    foundry_root: Path
    evaluated_at: datetime
    source_platform_id: str
    executed_observations: tuple[ExecutedObservation, ...]
    pattern_proposals: tuple[LandingStructurePatternProposal, ...]
    lesson_seeds: tuple[CrossPlatformLessonSeed, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.cross-platform-learning-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "source_platform_id": self.source_platform_id,
            "executed_observations": [item.to_document() for item in self.executed_observations],
            "pattern_proposals": [item.to_document() for item in self.pattern_proposals],
            "lesson_seeds": [item.to_document() for item in self.lesson_seeds],
            "report_digest": self.report_digest,
        }


def _validate_https_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CrossPlatformLearningRejected("URL_INVALID", "only HTTPS public URLs are allowed")


def resolve_platform_url(
    foundry_root: Path,
    platform_id: str,
    policy: CrossPlatformLearningPolicy,
) -> str | None:
    for configured_id, url in policy.platform_urls:
        if configured_id == platform_id:
            return url
    path = _landing_intent_path(foundry_root, platform_id)
    if path is None:
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    platform = document.get("platform") or {}
    url = platform.get("public_url")
    if isinstance(url, str) and url.startswith("https://"):
        return url
    return None


def flow_markers_from_html(text: str) -> tuple[str, ...]:
    markers: list[str] = []
    if re.search(r"step\s*1|step\s*2|step\s*3|step\s*4", text, re.IGNORECASE):
        markers.extend(
            [
                "flow/step-select",
                "flow/step-info-payment",
                "flow/step-e-contract",
                "flow/step-complete",
            ]
        )
    if re.search(r"전자|계약|esign|sign", text, re.IGNORECASE):
        markers.append("flow/electronic-contract")
    if re.search(r"비교|comparison|others", text, re.IGNORECASE):
        markers.append("surface/comparison-matrix")
    if re.search(r"마이페이지|dashboard|대시보드", text, re.IGNORECASE):
        markers.append("surface/mypage-dashboard")
    if re.search(r"faq|자주하는\s*질문", text, re.IGNORECASE):
        markers.append("surface/faq-accordion")
    if re.search(r"cta|계약하기|시작", text, re.IGNORECASE):
        markers.append("surface/hero-primary-cta")
    return tuple(sorted(set(markers)))


def build_surface_observation_document(
    *,
    platform_id: str,
    source_url: str,
    payload: bytes,
    now: datetime,
) -> dict[str, object]:
    if now.tzinfo is None:
        raise CrossPlatformLearningRejected("TIMESTAMP", "timezone-aware timestamp required")
    signals = structural_signals_from_public_html(payload, context=platform_id)
    text = payload.decode("utf-8", errors="replace")
    policy_routes = flow_markers_from_html(text)
    observation = {
        "schema_version": "apf.public-surface-observation/v1",
        "platform_id": platform_id,
        "observed_at": now.isoformat(),
        "rights_posture": "PUBLIC_OBSERVATION",
        "source_url": source_url,
        "openapi_paths": [],
        "policy_route_refs": list(policy_routes),
        "js_structures": [],
        "observation_signals": signals,
        "observation_digest": "",
        "copy_prohibited": True,
        "verbatim_storage": False,
        "maximum_outcome": "STRUCTURAL_OBSERVATION",
    }
    observation["observation_digest"] = digest_document(
        {key: value for key, value in observation.items() if key != "observation_digest"}
    )
    return observation


def fetch_public_payload(url: str, *, max_bytes: int = 500_000) -> bytes:
    _validate_https_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "ARKAON-Pattern-Foundry/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(max_bytes)


def infer_routes_from_landing_intent(foundry_root: Path, platform_id: str) -> frozenset[str]:
    tokens = load_sought_capability_tokens(foundry_root, platform_id)
    routes: set[str] = set()
    for token in tokens:
        for route in _TOKEN_ROUTE_MAP.get(token, ()):
            routes.add(route)
    path = _landing_intent_path(foundry_root, platform_id)
    if path is not None:
        document = json.loads(path.read_text(encoding="utf-8"))
        signals = (document.get("landing_intent") or {}).get("signal") or ()
        signal_map = {
            "four_step_process_section": _TOKEN_ROUTE_MAP.get("landing-pattern:four-step-process", ()),
            "electronic_contract_step": _TOKEN_ROUTE_MAP.get("landing-pattern:e-contract-flow", ()),
            "comparison_matrix_present": _TOKEN_ROUTE_MAP.get("landing-pattern:comparison-table", ()),
            "mypage_dashboard_mock": _TOKEN_ROUTE_MAP.get("landing-pattern:mypage-dashboard", ()),
            "single_primary_cta": _TOKEN_ROUTE_MAP.get("landing-pattern:hero-single-cta", ()),
            "faq_accordion": _TOKEN_ROUTE_MAP.get("landing-signal:faq_accordion", ()),
        }
        for signal in signals:
            if isinstance(signal, str):
                routes.update(signal_map.get(signal, ()))
    return frozenset(routes)


def load_surface_observation(foundry_root: Path, platform_id: str) -> dict[str, object] | None:
    store = foundry_root / "state" / "surface-observations"
    if not store.is_dir():
        return None
    latest: tuple[datetime, dict[str, object]] | None = None
    for path in store.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if document.get("platform_id") != platform_id:
            continue
        observed_raw = document.get("observed_at")
        try:
            observed_at = datetime.fromisoformat(str(observed_raw)) if observed_raw else datetime.min.replace(tzinfo=UTC)
        except ValueError:
            observed_at = datetime.min.replace(tzinfo=UTC)
        if latest is None or observed_at >= latest[0]:
            latest = (observed_at, document)
    return latest[1] if latest else None


def _route_refs_from_observation(document: dict[str, object]) -> frozenset[str]:
    refs = document.get("policy_route_refs") or ()
    return frozenset(str(item) for item in refs if isinstance(item, str))


def _merged_platform_routes(foundry_root: Path, platform_id: str, observation: dict[str, object] | None) -> frozenset[str]:
    routes = infer_routes_from_landing_intent(foundry_root, platform_id)
    if observation is not None:
        routes = routes | _route_refs_from_observation(observation)
    return routes


def _tokens_supported_by_routes(
    sought_tokens: frozenset[str],
    platform_routes: dict[str, frozenset[str]],
) -> dict[str, tuple[str, ...]]:
    supported: dict[str, tuple[str, ...]] = {}
    for token in sorted(sought_tokens):
        route_candidates = _TOKEN_ROUTE_MAP.get(token, ())
        if not route_candidates:
            continue
        platforms: list[str] = []
        shared_routes: list[str] = []
        for platform_id, routes in platform_routes.items():
            matched = tuple(route for route in route_candidates if route in routes)
            if matched:
                platforms.append(platform_id)
                shared_routes.extend(matched)
        if len(platforms) >= 2:
            supported[token] = tuple(sorted(set(shared_routes)))
    return supported


def compare_and_abstract_patterns(
    *,
    source_platform_id: str,
    target_platform_ids: tuple[str, ...],
    sought_tokens: frozenset[str],
    platform_routes: dict[str, frozenset[str]],
    platform_digests: dict[str, str],
    minimum_platforms: int,
) -> tuple[LandingStructurePatternProposal, ...]:
    proposals: list[LandingStructurePatternProposal] = []
    supported = _tokens_supported_by_routes(sought_tokens, platform_routes)
    for token, shared_routes in supported.items():
        platforms_with_token = [
            platform_id
            for platform_id in (source_platform_id, *target_platform_ids)
            if platform_id in platform_routes
            and any(route in platform_routes[platform_id] for route in shared_routes)
        ]
        unique_platforms = tuple(sorted(set(platforms_with_token)))
        if len(unique_platforms) < minimum_platforms:
            continue
        pattern_slug = token.split(":", 1)[-1].replace("_", "-")
        pattern_id = f"landing.cross-platform.{pattern_slug}"
        digests = tuple(
            sorted(platform_digests[platform_id] for platform_id in unique_platforms if platform_id in platform_digests)
        )
        proposals.append(
            LandingStructurePatternProposal(
                pattern_id=pattern_id,
                pattern_token=token,
                platform_ids=unique_platforms,
                shared_route_refs=shared_routes,
                evidence_digests=digests,
                summary=(
                    f"{', '.join(unique_platforms)}에서 {token} structural evidence가 "
                    f"공유 route({', '.join(shared_routes)})로 관측되었습니다."
                ),
            )
        )
    return tuple(proposals)


def _lesson_seed_for_pattern(
    *,
    source_platform_id: str,
    proposal: LandingStructurePatternProposal,
) -> CrossPlatformLessonSeed:
    case_id = f"xplat-{source_platform_id}-{sha256(proposal.pattern_token.encode()).hexdigest()[:12]}"
    evidence_digest = sha256(
        json.dumps(
            {
                "pattern_id": proposal.pattern_id,
                "platform_ids": proposal.platform_ids,
                "shared_route_refs": proposal.shared_route_refs,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return CrossPlatformLessonSeed(
        case_id=case_id,
        pattern_id=proposal.pattern_id,
        platform_scope=source_platform_id,
        principle="cross-platform structural compare에서 공통 funnel/route가 확인되면 clean-room landing pattern으로 추상화한다",
        reusable_pattern=proposal.pattern_token,
        evidence_digest=evidence_digest,
    )


class CrossPlatformLearningEngine:
    def __init__(self, *, foundry_root: Path, policy: CrossPlatformLearningPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-cross-platform-learning.json"
        self.policy = policy or CrossPlatformLearningPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "cross-platform-learning"
        self.pattern_root = self.foundry_root / "knowledge" / "landing-structure-patterns" / "proposed"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        *,
        resolution_report: AnalysisTargetResolutionReport,
        now: datetime,
        dry_run: bool,
        fetch_payload: Callable[[str], bytes] | None = None,
    ) -> CrossPlatformLearningReport:
        if now.tzinfo is None:
            raise CrossPlatformLearningRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            digest = sha256(b"disabled").hexdigest()
            source = resolution_report.last_user_site.platform_id if resolution_report.last_user_site else "UNKNOWN"
            return CrossPlatformLearningReport(
                foundry_root=self.foundry_root,
                evaluated_at=now,
                source_platform_id=source,
                executed_observations=(),
                pattern_proposals=(),
                lesson_seeds=(),
                report_digest=digest,
            )
        last_site = resolution_report.last_user_site
        if last_site is None:
            raise CrossPlatformLearningRejected("NO_LAST_SITE", "cross-platform learning requires last user site")
        source_platform_id = last_site.platform_id
        sought = frozenset(last_site.sought_capability_tokens) or load_sought_capability_tokens(
            self.foundry_root, source_platform_id
        )
        targets = resolution_report.targets
        if not targets:
            fallback_ids = sorted(
                [
                    platform_id
                    for platform_id in list_landing_intent_platform_ids(self.foundry_root)
                    if platform_id != source_platform_id
                ],
                key=_platform_sort_key,
            )[: self.policy.max_fetches_per_run]
            targets = tuple(
                CrossPlatformTarget(
                    platform_id=platform_id,
                    capability_tokens=tuple(sorted(sought)),
                    rationale="wave1 fallback compare when resolution targets exhausted",
                )
                for platform_id in fallback_ids
            )
        fetcher = fetch_payload or fetch_public_payload
        executed: list[ExecutedObservation] = []
        platform_routes: dict[str, frozenset[str]] = {}
        platform_digests: dict[str, str] = {}

        fetch_count = 0
        source_url = resolve_platform_url(self.foundry_root, source_platform_id, self.policy)
        if (
            source_url
            and self.policy.execute_public_fetch
            and fetch_count < self.policy.max_fetches_per_run
        ):
            fetch_count += 1
            source_payload = fetcher(source_url)
            source_observation = build_surface_observation_document(
                platform_id=source_platform_id,
                source_url=source_url,
                payload=source_payload,
                now=now,
            )
            store = self.foundry_root / "state" / "surface-observations"
            if not dry_run:
                store.mkdir(parents=True, exist_ok=True)
                source_path = store / f"{source_platform_id}-{source_observation['observation_digest'][:12]}.json"
                source_path.write_text(
                    json.dumps(source_observation, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            source_obs = source_observation
            platform_routes[source_platform_id] = _merged_platform_routes(
                self.foundry_root, source_platform_id, source_obs
            )
            platform_digests[source_platform_id] = str(source_observation["observation_digest"])
        else:
            source_obs = load_surface_observation(self.foundry_root, source_platform_id)
            platform_routes[source_platform_id] = _merged_platform_routes(
                self.foundry_root, source_platform_id, source_obs
            )
            if source_obs is not None:
                platform_digests[source_platform_id] = str(source_obs.get("observation_digest", ""))
        target_ids = tuple(target.platform_id for target in targets)
        for target in targets:
            url = resolve_platform_url(self.foundry_root, target.platform_id, self.policy)
            if url is None or not self.policy.execute_public_fetch:
                existing = load_surface_observation(self.foundry_root, target.platform_id)
                merged = _merged_platform_routes(self.foundry_root, target.platform_id, existing)
                if merged:
                    platform_routes[target.platform_id] = merged
                    if existing is not None:
                        platform_digests[target.platform_id] = str(existing.get("observation_digest", ""))
                    else:
                        platform_digests[target.platform_id] = sha256(
                            json.dumps(sorted(merged), sort_keys=True).encode()
                        ).hexdigest()
                executed.append(
                    ExecutedObservation(
                        platform_id=target.platform_id,
                        source_url="",
                        observation_path="",
                        observation_digest=platform_digests.get(target.platform_id, ""),
                        policy_route_refs=tuple(sorted(platform_routes.get(target.platform_id, ()))),
                        skipped_fetch=True,
                        skip_reason="NO_PUBLIC_URL" if url is None else "FETCH_DISABLED",
                    )
                )
                continue
            if fetch_count >= self.policy.max_fetches_per_run:
                executed.append(
                    ExecutedObservation(
                        platform_id=target.platform_id,
                        source_url=url,
                        observation_path="",
                        observation_digest="",
                        policy_route_refs=(),
                        skipped_fetch=True,
                        skip_reason="FETCH_BUDGET_EXCEEDED",
                    )
                )
                continue
            fetch_count += 1
            payload = fetcher(url)
            observation = build_surface_observation_document(
                platform_id=target.platform_id,
                source_url=url,
                payload=payload,
                now=now,
            )
            store = self.foundry_root / "state" / "surface-observations"
            observation_path = store / f"{target.platform_id}-{observation['observation_digest'][:12]}.json"
            if not dry_run:
                store.mkdir(parents=True, exist_ok=True)
                observation_path.write_text(
                    json.dumps(observation, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            digest = str(observation["observation_digest"])
            platform_routes[target.platform_id] = _merged_platform_routes(
                self.foundry_root, target.platform_id, observation
            )
            platform_digests[target.platform_id] = digest
            routes = tuple(sorted(platform_routes[target.platform_id]))
            executed.append(
                ExecutedObservation(
                    platform_id=target.platform_id,
                    source_url=url,
                    observation_path=observation_path.relative_to(self.foundry_root).as_posix()
                    if not dry_run
                    else observation_path.as_posix(),
                    observation_digest=digest,
                    policy_route_refs=routes,
                )
            )

        pattern_proposals: tuple[LandingStructurePatternProposal, ...] = ()
        if self.policy.emit_landing_pattern_proposals and sought:
            pattern_proposals = compare_and_abstract_patterns(
                source_platform_id=source_platform_id,
                target_platform_ids=target_ids,
                sought_tokens=sought,
                platform_routes=platform_routes,
                platform_digests=platform_digests,
                minimum_platforms=self.policy.minimum_platforms_for_pattern,
            )
            if not dry_run:
                self.pattern_root.mkdir(parents=True, exist_ok=True)
                for proposal in pattern_proposals:
                    path = self.pattern_root / f"{proposal.pattern_id}.json"
                    if not path.is_file():
                        path.write_text(
                            json.dumps(proposal.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                            encoding="utf-8",
                        )

        lesson_seeds = tuple(
            _lesson_seed_for_pattern(source_platform_id=source_platform_id, proposal=proposal)
            for proposal in pattern_proposals
        )

        digest_payload = {
            "evaluated_at": now.isoformat(),
            "source_platform_id": source_platform_id,
            "executed_count": len(executed),
            "pattern_count": len(pattern_proposals),
            "lesson_count": len(lesson_seeds),
        }
        report_digest = sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
        report = CrossPlatformLearningReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            source_platform_id=source_platform_id,
            executed_observations=tuple(executed),
            pattern_proposals=pattern_proposals,
            lesson_seeds=lesson_seeds,
            report_digest=report_digest,
        )
        if not dry_run:
            dated = self.store_root / f"{now.strftime('%Y-%m-%d')}-{report_digest[:12]}.json"
            dated.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (self.store_root / "latest.json").write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return report
