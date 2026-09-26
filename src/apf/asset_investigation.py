"""Rank investigation priorities so ARKAON pursues the strongest evidence-bound assets first."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .owned_platform_metadata import MetadataPilotError, validate_metadata_pilot
from .pattern_catalog import PatternCatalogError, validate_catalog
from .research_watch import ResearchWatchRegistry, WatchEvent


class AssetInvestigationRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InvestigationKind(str, Enum):
    RESEARCH_DELTA = "RESEARCH_DELTA"
    PATTERN_CANDIDATE = "PATTERN_CANDIDATE"
    OWNED_PILOT_GAP = "OWNED_PILOT_GAP"
    PROMOTION_PENDING = "PROMOTION_PENDING"
    SURFACE_SIGNAL = "SURFACE_SIGNAL"


@dataclass(frozen=True)
class AssetInvestigationPolicy:
    automatic_promotion_allowed: bool = False
    automatic_learning_allowed: bool = False
    production_change_allowed: bool = False
    max_report_items: int = 10
    emit_research_packet: bool = True
    minimum_score_for_packet: int = 50

    @classmethod
    def load(cls, path: Path) -> AssetInvestigationPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-asset-investigation/v1":
            raise AssetInvestigationRejected("POLICY_SCHEMA", "unsupported asset investigation schema")
        if (
            document.get("automatic_promotion_allowed")
            or document.get("automatic_learning_allowed")
            or document.get("production_change_allowed")
        ):
            raise AssetInvestigationRejected("POLICY_FORBIDDEN", "asset investigation must remain advisory")
        return cls(
            automatic_promotion_allowed=bool(document.get("automatic_promotion_allowed")),
            automatic_learning_allowed=bool(document.get("automatic_learning_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            max_report_items=max(1, int(document.get("max_report_items", 10))),
            emit_research_packet=bool(document.get("emit_research_packet", True)),
            minimum_score_for_packet=int(document.get("minimum_score_for_packet", 50)),
        )


@dataclass(frozen=True)
class InvestigationPriority:
    rank: int
    score: int
    kind: InvestigationKind
    asset_id: str
    platform_id: str
    summary: str
    evidence_refs: tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "score": self.score,
            "kind": self.kind.value,
            "asset_id": self.asset_id,
            "platform_id": self.platform_id,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class AssetInvestigationReport:
    foundry_root: Path
    evaluated_at: datetime
    catalog_revision: str | None
    priorities: tuple[InvestigationPriority, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.asset-investigation-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "catalog_revision": self.catalog_revision,
            "report_digest": self.report_digest,
            "priorities": [item.to_document() for item in self.priorities],
        }


def _load_candidates(foundry_root: Path) -> list[dict]:
    directory = foundry_root / "knowledge" / "patterns" / "candidates"
    if not directory.is_dir():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def _score_research_event(event: WatchEvent) -> InvestigationPriority | None:
    if event.changed and event.previous_digest is not None:
        score = 100
        summary = f"research watch {event.watch_id} digest changed; prioritize re-validation"
    elif event.previous_digest is None:
        score = 80
        summary = f"research watch {event.watch_id} baseline established; schedule deep review"
    else:
        return None
    return InvestigationPriority(
        rank=0,
        score=score,
        kind=InvestigationKind.RESEARCH_DELTA,
        asset_id=event.watch_id,
        platform_id=event.platform_id,
        summary=summary,
        evidence_refs=(f"state/research-watch/digests.json#{event.watch_id}",),
    )


def _score_pattern_candidate(package: dict, *, source_usage: dict[str, int]) -> InvestigationPriority:
    refs = tuple(package.get("source_refs") or ())
    unique_sources = sum(1 for ref in refs if source_usage.get(ref, 0) == 1)
    test_count = len(package.get("verification_test_ids") or ())
    score = 45 + unique_sources * 8 + min(test_count, 3) * 5
    return InvestigationPriority(
        rank=0,
        score=score,
        kind=InvestigationKind.PATTERN_CANDIDATE,
        asset_id=str(package["pattern_id"]),
        platform_id="ARKAON_FOUNDRY",
        summary=(
            f"pattern candidate with {len(refs)} source refs and {unique_sources} unique evidence anchors; "
            "rank for eternian review when evidence is strongest"
        ),
        evidence_refs=refs,
    )


def _score_owned_pilot(foundry_root: Path, path: Path) -> InvestigationPriority | None:
    try:
        result = validate_metadata_pilot(path.read_bytes())
    except (MetadataPilotError, OSError):
        return None
    if result.repository_connection != "NOT_RUN_UNAVAILABLE":
        return None
    score = 65
    return InvestigationPriority(
        rank=0,
        score=score,
        kind=InvestigationKind.OWNED_PILOT_GAP,
        asset_id=result.platform_id,
        platform_id=result.platform_id,
        summary=(
            f"{result.platform_name}: metadata pilot complete but live repository investigation "
            "NOT_RUN; highest-value owned-platform gap"
        ),
        evidence_refs=(path.relative_to(foundry_root).as_posix(),),
    )


def _score_surface_observations(foundry_root: Path) -> list[InvestigationPriority]:
    store = foundry_root / "state" / "surface-observations"
    if not store.is_dir():
        return []
    items: list[InvestigationPriority] = []
    for path in sorted(store.glob("*.json"), reverse=True)[:5]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        platform_id = str(document.get("platform_id", "UNKNOWN"))
        digest = str(document.get("observation_digest", path.stem))
        items.append(
            InvestigationPriority(
                rank=0,
                score=52,
                kind=InvestigationKind.SURFACE_SIGNAL,
                asset_id=digest[:16],
                platform_id=platform_id,
                summary=f"{platform_id}: public surface structural digest available; compare for best reusable patterns",
                evidence_refs=(path.relative_to(foundry_root).as_posix(),),
            )
        )
    return items


def _score_promotion_pending(foundry_root: Path, *, catalog_revision: str | None) -> InvestigationPriority | None:
    manifest_path = foundry_root / "config" / "pattern-promotion-manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pending = 30 - len(manifest.get("decisions") or [])
    if pending <= 0:
        return None
    return InvestigationPriority(
        rank=0,
        score=55,
        kind=InvestigationKind.PROMOTION_PENDING,
        asset_id="pattern-catalog",
        platform_id="ARKAON_FOUNDRY",
        summary=f"{pending} public pattern candidates await external eternian signatures for best-asset promotion",
        evidence_refs=("config/pattern-promotion-manifest.json", "knowledge/patterns/candidates/"),
    )


class AssetInvestigationHarness:
    """Search and rank asset signals; advisory-only, no auto-promotion."""

    def __init__(self, *, foundry_root: Path, policy: AssetInvestigationPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy = policy or AssetInvestigationPolicy.load(
            self.foundry_root / "config" / "arkaon-asset-investigation.json"
        )

    def run(self, *, now: datetime, watch_events: tuple[WatchEvent, ...] = ()) -> AssetInvestigationReport:
        if now.tzinfo is None:
            raise AssetInvestigationRejected("TIMESTAMP", "timezone-aware timestamp required")
        candidates = _load_candidates(self.foundry_root)
        catalog_revision: str | None = None
        if candidates:
            try:
                catalog_revision = validate_catalog(candidates, self.foundry_root)
            except PatternCatalogError:
                catalog_revision = None
        source_usage: dict[str, int] = {}
        for package in candidates:
            for ref in package.get("source_refs") or []:
                source_usage[str(ref)] = source_usage.get(str(ref), 0) + 1
        scored: list[InvestigationPriority] = []
        if not watch_events:
            watch_events = ResearchWatchRegistry(foundry_root=self.foundry_root).detect_changes(now=now)
        for event in watch_events:
            item = _score_research_event(event)
            if item is not None:
                scored.append(item)
        for package in candidates:
            scored.append(_score_pattern_candidate(package, source_usage=source_usage))
        pilots_dir = self.foundry_root / "knowledge" / "pilots"
        if pilots_dir.is_dir():
            for path in sorted(pilots_dir.glob("*-041.json")):
                item = _score_owned_pilot(self.foundry_root, path)
                if item is not None:
                    scored.append(item)
        scored.extend(_score_surface_observations(self.foundry_root))
        pending = _score_promotion_pending(self.foundry_root, catalog_revision=catalog_revision)
        if pending is not None:
            scored.append(pending)
        scored.sort(key=lambda item: (-item.score, item.asset_id))
        top = scored[: self.policy.max_report_items]
        priorities = tuple(
            InvestigationPriority(
                rank=index + 1,
                score=item.score,
                kind=item.kind,
                asset_id=item.asset_id,
                platform_id=item.platform_id,
                summary=item.summary,
                evidence_refs=item.evidence_refs,
            )
            for index, item in enumerate(top)
        )
        document = {
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": now.isoformat(),
            "catalog_revision": catalog_revision,
            "priorities": [item.to_document() for item in priorities],
        }
        digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        return AssetInvestigationReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            catalog_revision=catalog_revision,
            priorities=priorities,
            report_digest=digest,
        )

    def persist(self, report: AssetInvestigationReport) -> Path:
        store = self.foundry_root / "state" / "asset-investigation"
        store.mkdir(parents=True, exist_ok=True)
        target = store / f"{report.evaluated_at.strftime('%Y-%m-%d')}-{report.report_digest[:16]}.json"
        document = report.to_document()
        document["report_digest"] = report.report_digest
        target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return target
