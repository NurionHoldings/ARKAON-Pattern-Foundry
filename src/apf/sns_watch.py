"""Periodic SNS structural analysis — detect feature/environment/format changes without verbatim posts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from .collector_service import SafeHttpsFetcher
from .continuous_collection import CollectionCandidate
from .external_learning import SourceKind


class SNSWatchRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SNSSourceKind(str, Enum):
    LOCAL_MANIFEST = "LOCAL_MANIFEST"
    PUBLIC_HTTPS_PROFILE = "PUBLIC_HTTPS_PROFILE"


class SNSChangeKind(str, Enum):
    BASELINE = "BASELINE"
    FEATURE_CHANGE = "FEATURE_CHANGE"
    ENVIRONMENT_CHANGE = "ENVIRONMENT_CHANGE"
    FORMAT_CHANGE = "FORMAT_CHANGE"
    SURFACE_CHANGE = "SURFACE_CHANGE"
    CLICK_SURGE = "CLICK_SURGE"
    TREND_SHIFT = "TREND_SHIFT"


@dataclass(frozen=True)
class SNSWatchPolicy:
    enabled: bool = True
    timezone: str = "Asia/Seoul"
    analysis_hours: tuple[int, ...] = (0, 6, 12, 18)
    automatic_learning: bool = False
    production_change_allowed: bool = False
    competitor_copy_allowed: bool = False
    verbatim_post_storage_allowed: bool = False
    max_response_bytes: int = 500_000

    @classmethod
    def load(cls, path: Path) -> SNSWatchPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.sns-watch/v1":
            raise SNSWatchRejected("POLICY_SCHEMA", "unsupported sns watch schema")
        if (
            document.get("automatic_learning")
            or document.get("production_change_allowed")
            or document.get("competitor_copy_allowed")
            or document.get("verbatim_post_storage_allowed")
        ):
            raise SNSWatchRejected("POLICY_FORBIDDEN", "sns watch must remain research-only and non-verbatim")
        hours = tuple(int(item) for item in (document.get("analysis_hours") or (0, 6, 12, 18)))
        for hour in hours:
            if not 0 <= hour <= 23:
                raise SNSWatchRejected("HOUR_INVALID", f"analysis hour must be 0-23, got {hour}")
        return cls(
            enabled=bool(document.get("enabled", True)),
            timezone=str(document.get("timezone", "Asia/Seoul")),
            analysis_hours=hours,
            automatic_learning=bool(document.get("automatic_learning")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            competitor_copy_allowed=bool(document.get("competitor_copy_allowed")),
            verbatim_post_storage_allowed=bool(document.get("verbatim_post_storage_allowed")),
            max_response_bytes=int(document.get("max_response_bytes", 500_000)),
        )


@dataclass(frozen=True)
class SNSTarget:
    watch_id: str
    kind: SNSSourceKind
    platform_id: str
    path: str = ""
    locator: str = ""
    domain_ids: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class SNSStructuralObservation:
    watch_id: str
    platform_id: str
    source_kind: SNSSourceKind
    signals: dict[str, object]
    structural_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.sns-structural-observation/v1",
            "watch_id": self.watch_id,
            "platform_id": self.platform_id,
            "source_kind": self.source_kind.value,
            "signals": self.signals,
            "structural_digest": self.structural_digest,
            "verbatim_post_storage": False,
        }


@dataclass(frozen=True)
class SNSEvent:
    watch_id: str
    platform_id: str
    source_kind: SNSSourceKind
    change_kind: SNSChangeKind
    previous_digest: str | None
    current_digest: str
    signal_delta: dict[str, object]
    domain_ids: tuple[str, ...]
    observed_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.sns-watch-event/v1",
            "watch_id": self.watch_id,
            "platform_id": self.platform_id,
            "source_kind": self.source_kind.value,
            "change_kind": self.change_kind.value,
            "previous_digest": self.previous_digest,
            "current_digest": self.current_digest,
            "signal_delta": self.signal_delta,
            "domain_ids": list(self.domain_ids),
            "observed_at": self.observed_at.isoformat(),
            "verbatim_post_storage": False,
            "maximum_outcome": "RESEARCH_PACKET",
        }


_META_PROPERTY = re.compile(r'<meta[^>]+property=["\']([^"\']+)["\']', re.IGNORECASE)
_LINK_HREF = re.compile(r"<a\b[^>]*\bhref=", re.IGNORECASE)
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc=", re.IGNORECASE)
_IFRAME = re.compile(r"<iframe\b", re.IGNORECASE)
_VIDEO = re.compile(r"<video\b", re.IGNORECASE)


def _digest_document(document: dict[str, object]) -> str:
    return sha256(json.dumps(document, sort_keys=True).encode("utf-8")).hexdigest()


def _link_count_bin(count: int) -> str:
    if count <= 1:
        return "0-1"
    if count <= 3:
        return "2-3"
    if count <= 5:
        return "4-5"
    return "6+"


def structural_signals_from_html(payload: bytes) -> dict[str, object]:
    text = payload.decode("utf-8", errors="replace")
    lowered = text.casefold()
    for forbidden in ("password", "credential", "access_token", "sessionid"):
        if forbidden in lowered:
            raise SNSWatchRejected("FORBIDDEN_CONTENT", "sns observation blocked sensitive marker")
    og_properties = sorted({match.group(1).casefold() for match in _META_PROPERTY.finditer(text)})
    link_count = len(_LINK_HREF.findall(text))
    script_count = len(_SCRIPT_SRC.findall(text))
    return {
        "og_property_count": len(og_properties),
        "og_property_samples": og_properties[:8],
        "link_count_bin": _link_count_bin(link_count),
        "script_src_count_bin": _link_count_bin(script_count),
        "has_iframe": bool(_IFRAME.search(text)),
        "has_video_tag": bool(_VIDEO.search(text)),
        "payload_bytes_bin": _link_count_bin(max(1, len(payload) // 100_000)),
    }


def _trend_summary_from_manifest(signals: dict[str, object]) -> dict[str, object]:
    surge_bins = frozenset({"surge", "explosive", "very-high"})
    category_tags: set[str] = set()
    surge_item_ids: set[str] = set()
    trend_count = 0
    surge_count = 0
    for raw in signals.get("trend_items") or ():
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id", "")).strip()
        category_tag = str(raw.get("category_tag", "")).strip()
        velocity = str(raw.get("click_velocity_bin", "")).strip()
        if not item_id or not category_tag:
            continue
        trend_count += 1
        category_tags.add(category_tag)
        if velocity in surge_bins:
            surge_count += 1
            surge_item_ids.add(item_id)
    return {
        "trend_item_count": trend_count,
        "trend_surge_count": surge_count,
        "trend_category_tags": sorted(category_tags),
        "trend_surge_item_ids": sorted(surge_item_ids),
    }


def structural_signals_from_manifest(document: dict[str, object]) -> dict[str, object]:
    if document.get("verbatim_post_storage"):
        raise SNSWatchRejected("FORBIDDEN_MANIFEST", "verbatim post storage is not allowed")
    signals = document.get("observation_signals")
    if not isinstance(signals, dict):
        raise SNSWatchRejected("MANIFEST_SIGNALS", "sns manifest requires observation_signals object")
    base = {
        "link_count_bin": signals.get("link_count_bin"),
        "format_tags": sorted(str(item) for item in (signals.get("format_tags") or ()) if str(item).strip()),
        "feature_tags": sorted(str(item) for item in (signals.get("feature_tags") or ()) if str(item).strip()),
        "environment_tags": sorted(
            str(item) for item in (signals.get("environment_tags") or ()) if str(item).strip()
        ),
        "channel_kind": document.get("channel_kind", "UNKNOWN"),
    }
    base.update(_trend_summary_from_manifest(signals))
    return base


def classify_signal_delta(
    *,
    previous: dict[str, object] | None,
    current: dict[str, object],
) -> tuple[SNSChangeKind, dict[str, object]]:
    if previous is None:
        return SNSChangeKind.BASELINE, {"status": "initial_observation"}
    delta: dict[str, object] = {}
    for key in sorted(set(previous) | set(current)):
        if previous.get(key) != current.get(key):
            delta[key] = {"before": previous.get(key), "after": current.get(key)}
    if not delta:
        return SNSChangeKind.SURFACE_CHANGE, {"status": "digest_changed_without_signal_diff"}
    env_keys = {"environment_tags", "payload_bytes_bin", "script_src_count_bin", "has_iframe", "has_video_tag"}
    feature_keys = {"feature_tags", "og_property_samples", "og_property_count"}
    format_keys = {"format_tags", "link_count_bin"}
    trend_keys = {"trend_surge_count", "trend_surge_item_ids", "trend_category_tags", "trend_item_count"}
    changed_keys = set(delta)
    if "trend_surge_count" in changed_keys or "trend_surge_item_ids" in changed_keys:
        before = previous.get("trend_surge_count", 0) if previous else 0
        after = current.get("trend_surge_count", 0)
        if isinstance(before, int) and isinstance(after, int) and after > before:
            return SNSChangeKind.CLICK_SURGE, delta
    if changed_keys & trend_keys:
        return SNSChangeKind.TREND_SHIFT, delta
    if changed_keys & env_keys:
        return SNSChangeKind.ENVIRONMENT_CHANGE, delta
    if changed_keys & feature_keys:
        return SNSChangeKind.FEATURE_CHANGE, delta
    if changed_keys & format_keys:
        return SNSChangeKind.FORMAT_CHANGE, delta
    return SNSChangeKind.SURFACE_CHANGE, delta


def load_sns_targets(foundry_root: Path) -> tuple[SNSTarget, ...]:
    path = foundry_root / "config" / "sns-watch-sources.json"
    if not path.is_file():
        return ()
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "apf.sns-watch-sources/v1":
        raise SNSWatchRejected("SOURCES_SCHEMA", "unsupported sns watch sources schema")
    targets: list[SNSTarget] = []
    for item in document.get("sources") or ():
        kind = SNSSourceKind(str(item.get("kind", SNSSourceKind.LOCAL_MANIFEST.value)))
        targets.append(
            SNSTarget(
                watch_id=str(item["watch_id"]),
                kind=kind,
                platform_id=str(item.get("platform_id", "ARKAON_FOUNDRY")),
                path=str(item.get("path", "")),
                locator=str(item.get("locator", "")),
                domain_ids=tuple(str(v) for v in (item.get("domain_ids") or ()) if str(v).strip()),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return tuple(targets)


class SNSWatchRegistry:
    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy = SNSWatchPolicy.load(self.foundry_root / "config" / "arkaon-sns-watch.json")
        self.state_path = self.foundry_root / "state" / "sns-watch" / "digests.json"
        self.last_run_path = self.foundry_root / "state" / "sns-watch" / "last-run.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._digests: dict[str, str] = {}
        self._signals: dict[str, dict[str, object]] = {}
        if self.state_path.is_file():
            document = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._digests = {str(k): str(v) for k, v in (document.get("digests") or {}).items()}
            raw_signals = document.get("signals") or {}
            self._signals = {
                str(key): dict(value) for key, value in raw_signals.items() if isinstance(value, dict)
            }

    def should_run_now(self, *, now: datetime) -> bool:
        if not self.policy.enabled:
            return False
        if now.tzinfo is None:
            raise SNSWatchRejected("TIMESTAMP", "timezone-aware timestamp required")
        local = now.astimezone(ZoneInfo(self.policy.timezone))
        if local.hour not in self.policy.analysis_hours:
            return False
        if self.last_run_path.is_file():
            last = json.loads(self.last_run_path.read_text(encoding="utf-8"))
            if last.get("local_date") == local.date().isoformat() and int(last.get("local_hour", -1)) == local.hour:
                return False
        return True

    def observe_target(self, target: SNSTarget) -> SNSStructuralObservation:
        if target.kind is SNSSourceKind.LOCAL_MANIFEST:
            manifest = self.foundry_root / target.path
            if not manifest.is_file():
                raise SNSWatchRejected("MANIFEST_MISSING", f"sns manifest not found: {target.path}")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            signals = structural_signals_from_manifest(document)
        else:
            if not target.locator.startswith("https://"):
                raise SNSWatchRejected("LOCATOR_INVALID", "sns public profile must use HTTPS locator")
            fetcher = SafeHttpsFetcher()
            candidate = CollectionCandidate(
                source_id=target.watch_id,
                kind=SourceKind.OFFICIAL_STANDARD,
                locator=target.locator,
                intent_relevance=0.5,
            )
            payload = fetcher.fetch(candidate, self.policy.max_response_bytes)
            signals = structural_signals_from_html(payload)
        digest = _digest_document({"watch_id": target.watch_id, "signals": signals})
        return SNSStructuralObservation(
            watch_id=target.watch_id,
            platform_id=target.platform_id,
            source_kind=target.kind,
            signals=signals,
            structural_digest=digest,
        )

    def analyze(self, *, now: datetime, force: bool = False) -> tuple[SNSEvent, ...]:
        if not force and not self.should_run_now(now=now):
            return ()
        events: list[SNSEvent] = []
        for target in load_sns_targets(self.foundry_root):
            if not target.enabled:
                continue
            try:
                observation = self.observe_target(target)
            except (SNSWatchRejected, OSError, ValueError, json.JSONDecodeError):
                continue
            previous_digest = self._digests.get(target.watch_id)
            previous_signals = self._signals.get(target.watch_id)
            change_kind, signal_delta = classify_signal_delta(
                previous=previous_signals,
                current=observation.signals,
            )
            changed = previous_digest is None or previous_digest != observation.structural_digest
            if previous_digest is None or changed:
                self._digests[target.watch_id] = observation.structural_digest
                self._signals[target.watch_id] = observation.signals
            if not changed and previous_digest is not None:
                continue
            events.append(
                SNSEvent(
                    watch_id=target.watch_id,
                    platform_id=target.platform_id,
                    source_kind=target.kind,
                    change_kind=change_kind if previous_digest is not None else SNSChangeKind.BASELINE,
                    previous_digest=previous_digest,
                    current_digest=observation.structural_digest,
                    signal_delta=signal_delta,
                    domain_ids=target.domain_ids,
                    observed_at=now,
                )
            )
        if events or force:
            self._persist()
            local = now.astimezone(ZoneInfo(self.policy.timezone))
            self.last_run_path.write_text(
                json.dumps(
                    {
                        "schema_version": "apf.sns-watch-last-run/v1",
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
