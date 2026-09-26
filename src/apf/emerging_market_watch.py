"""Emerging market watch — detect new segments, demand shifts, and regulatory signals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

from .collector_service import SafeHttpsFetcher
from .continuous_collection import CollectionCandidate
from .external_learning import SourceKind
from .structural_surface_common import digest_document, structural_signals_from_public_html


class EmergingMarketWatchRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MarketSourceKind(str, Enum):
    LOCAL_MANIFEST = "LOCAL_MANIFEST"
    PUBLIC_HTTPS_INDEX = "PUBLIC_HTTPS_INDEX"


class MarketChangeKind(str, Enum):
    BASELINE = "BASELINE"
    NEW_MARKET_SEGMENT = "NEW_MARKET_SEGMENT"
    DEMAND_SHIFT = "DEMAND_SHIFT"
    REGULATORY_SIGNAL = "REGULATORY_SIGNAL"
    NOVELTY_RISE = "NOVELTY_RISE"
    MARKET_SURFACE_CHANGE = "MARKET_SURFACE_CHANGE"


@dataclass(frozen=True)
class EmergingMarketWatchPolicy:
    enabled: bool = True
    timezone: str = "Asia/Seoul"
    analysis_hours: tuple[int, ...] = (3, 9, 15, 21)
    automatic_learning: bool = False
    production_change_allowed: bool = False
    competitor_copy_allowed: bool = False
    verbatim_storage_allowed: bool = False
    max_response_bytes: int = 500_000

    @classmethod
    def load(cls, path: Path) -> EmergingMarketWatchPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.emerging-market-watch/v1":
            raise EmergingMarketWatchRejected("POLICY_SCHEMA", "unsupported emerging market watch schema")
        if (
            document.get("automatic_learning")
            or document.get("production_change_allowed")
            or document.get("competitor_copy_allowed")
            or document.get("verbatim_storage_allowed")
        ):
            raise EmergingMarketWatchRejected("POLICY_FORBIDDEN", "emerging market watch must remain research-only")
        hours = tuple(int(item) for item in (document.get("analysis_hours") or (3, 9, 15, 21)))
        return cls(
            enabled=bool(document.get("enabled", True)),
            timezone=str(document.get("timezone", "Asia/Seoul")),
            analysis_hours=hours,
            automatic_learning=bool(document.get("automatic_learning")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            competitor_copy_allowed=bool(document.get("competitor_copy_allowed")),
            verbatim_storage_allowed=bool(document.get("verbatim_storage_allowed")),
            max_response_bytes=int(document.get("max_response_bytes", 500_000)),
        )


@dataclass(frozen=True)
class MarketTarget:
    watch_id: str
    kind: MarketSourceKind
    platform_id: str
    path: str = ""
    locator: str = ""
    market_scope: str = "GENERAL"
    enabled: bool = True


@dataclass(frozen=True)
class EmergingMarketEvent:
    watch_id: str
    platform_id: str
    source_kind: MarketSourceKind
    market_scope: str
    change_kind: MarketChangeKind
    previous_digest: str | None
    current_digest: str
    signal_delta: dict[str, object]
    observed_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.emerging-market-event/v1",
            "watch_id": self.watch_id,
            "platform_id": self.platform_id,
            "source_kind": self.source_kind.value,
            "market_scope": self.market_scope,
            "change_kind": self.change_kind.value,
            "previous_digest": self.previous_digest,
            "current_digest": self.current_digest,
            "signal_delta": self.signal_delta,
            "observed_at": self.observed_at.isoformat(),
            "verbatim_storage": False,
            "maximum_outcome": "RESEARCH_PACKET",
        }


def market_signals_from_manifest(document: dict[str, object]) -> dict[str, object]:
    if document.get("verbatim_storage") or document.get("verbatim_post_storage"):
        raise EmergingMarketWatchRejected("FORBIDDEN_MANIFEST", "verbatim market storage is not allowed")
    signals = document.get("observation_signals")
    if not isinstance(signals, dict):
        raise EmergingMarketWatchRejected("MANIFEST_SIGNALS", "market manifest requires observation_signals")
    return {
        "market_scope": document.get("market_scope", "GENERAL"),
        "segment_tags": sorted(str(item) for item in (signals.get("segment_tags") or ()) if str(item).strip()),
        "demand_tags": sorted(str(item) for item in (signals.get("demand_tags") or ()) if str(item).strip()),
        "regulatory_tags": sorted(
            str(item) for item in (signals.get("regulatory_tags") or ()) if str(item).strip()
        ),
        "novelty_score_bin": signals.get("novelty_score_bin", "unknown"),
        "change_velocity_bin": signals.get("change_velocity_bin", "unknown"),
    }


def classify_market_delta(
    *,
    previous: dict[str, object] | None,
    current: dict[str, object],
) -> tuple[MarketChangeKind, dict[str, object]]:
    if previous is None:
        return MarketChangeKind.BASELINE, {"status": "initial_observation"}
    delta: dict[str, object] = {}
    for key in sorted(set(previous) | set(current)):
        if previous.get(key) != current.get(key):
            delta[key] = {"before": previous.get(key), "after": current.get(key)}
    if not delta:
        return MarketChangeKind.MARKET_SURFACE_CHANGE, {"status": "digest_changed_without_signal_diff"}
    changed = set(delta)
    if "segment_tags" in changed:
        return MarketChangeKind.NEW_MARKET_SEGMENT, delta
    if "demand_tags" in changed:
        return MarketChangeKind.DEMAND_SHIFT, delta
    if "regulatory_tags" in changed:
        return MarketChangeKind.REGULATORY_SIGNAL, delta
    if "novelty_score_bin" in changed or "change_velocity_bin" in changed:
        return MarketChangeKind.NOVELTY_RISE, delta
    return MarketChangeKind.MARKET_SURFACE_CHANGE, delta


def load_market_targets(foundry_root: Path) -> tuple[MarketTarget, ...]:
    path = foundry_root / "config" / "emerging-market-sources.json"
    if not path.is_file():
        return ()
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "apf.emerging-market-sources/v1":
        raise EmergingMarketWatchRejected("SOURCES_SCHEMA", "unsupported emerging market sources schema")
    targets: list[MarketTarget] = []
    for item in document.get("sources") or ():
        targets.append(
            MarketTarget(
                watch_id=str(item["watch_id"]),
                kind=MarketSourceKind(str(item.get("kind", MarketSourceKind.LOCAL_MANIFEST.value))),
                platform_id=str(item.get("platform_id", "ARKAON_FOUNDRY")),
                path=str(item.get("path", "")),
                locator=str(item.get("locator", "")),
                market_scope=str(item.get("market_scope", "GENERAL")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return tuple(targets)


class EmergingMarketWatchRegistry:
    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy = EmergingMarketWatchPolicy.load(
            self.foundry_root / "config" / "arkaon-emerging-market-watch.json"
        )
        self.state_path = self.foundry_root / "state" / "emerging-market-watch" / "digests.json"
        self.last_run_path = self.foundry_root / "state" / "emerging-market-watch" / "last-run.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._digests: dict[str, str] = {}
        self._signals: dict[str, dict[str, object]] = {}
        if self.state_path.is_file():
            document = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._digests = {str(k): str(v) for k, v in (document.get("digests") or {}).items()}
            self._signals = {
                str(k): dict(v) for k, v in (document.get("signals") or {}).items() if isinstance(v, dict)
            }

    def should_run_now(self, *, now: datetime) -> bool:
        if not self.policy.enabled:
            return False
        if now.tzinfo is None:
            raise EmergingMarketWatchRejected("TIMESTAMP", "timezone-aware timestamp required")
        local = now.astimezone(ZoneInfo(self.policy.timezone))
        if local.hour not in self.policy.analysis_hours:
            return False
        if self.last_run_path.is_file():
            last = json.loads(self.last_run_path.read_text(encoding="utf-8"))
            if last.get("local_date") == local.date().isoformat() and int(last.get("local_hour", -1)) == local.hour:
                return False
        return True

    def observe_target(self, target: MarketTarget) -> tuple[dict[str, object], str]:
        if target.kind is MarketSourceKind.LOCAL_MANIFEST:
            manifest = self.foundry_root / target.path
            if not manifest.is_file():
                raise EmergingMarketWatchRejected("MANIFEST_MISSING", f"market manifest missing: {target.path}")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            signals = market_signals_from_manifest(document)
        else:
            if not target.locator.startswith("https://"):
                raise EmergingMarketWatchRejected("LOCATOR_INVALID", "market index must use HTTPS")
            fetcher = SafeHttpsFetcher()
            candidate = CollectionCandidate(
                source_id=target.watch_id,
                kind=SourceKind.OFFICIAL_STANDARD,
                locator=target.locator,
                intent_relevance=0.55,
            )
            payload = fetcher.fetch(candidate, self.policy.max_response_bytes)
            signals = structural_signals_from_public_html(payload, context="emerging_market")
            signals["market_scope"] = target.market_scope
        digest = digest_document({"watch_id": target.watch_id, "signals": signals})
        return signals, digest

    def analyze(self, *, now: datetime, force: bool = False) -> tuple[EmergingMarketEvent, ...]:
        if not force and not self.should_run_now(now=now):
            return ()
        events: list[EmergingMarketEvent] = []
        for target in load_market_targets(self.foundry_root):
            if not target.enabled:
                continue
            try:
                signals, digest = self.observe_target(target)
            except (EmergingMarketWatchRejected, OSError, ValueError, json.JSONDecodeError):
                continue
            previous_digest = self._digests.get(target.watch_id)
            previous_signals = self._signals.get(target.watch_id)
            change_kind, signal_delta = classify_market_delta(previous=previous_signals, current=signals)
            changed = previous_digest is None or previous_digest != digest
            if previous_digest is None or changed:
                self._digests[target.watch_id] = digest
                self._signals[target.watch_id] = signals
            if not changed and previous_digest is not None:
                continue
            events.append(
                EmergingMarketEvent(
                    watch_id=target.watch_id,
                    platform_id=target.platform_id,
                    source_kind=target.kind,
                    market_scope=target.market_scope,
                    change_kind=change_kind if previous_digest is not None else MarketChangeKind.BASELINE,
                    previous_digest=previous_digest,
                    current_digest=digest,
                    signal_delta=signal_delta,
                    observed_at=now,
                )
            )
        if events or force:
            self._persist()
            local = now.astimezone(ZoneInfo(self.policy.timezone))
            self.last_run_path.write_text(
                json.dumps(
                    {
                        "schema_version": "apf.emerging-market-last-run/v1",
                        "local_date": local.date().isoformat(),
                        "local_hour": local.hour,
                        "observed_at": now.isoformat(),
                        "event_count": len(events),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        return tuple(events)

    def _persist(self) -> None:
        self.state_path.write_text(
            json.dumps(
                {"digests": self._digests, "signals": self._signals},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
