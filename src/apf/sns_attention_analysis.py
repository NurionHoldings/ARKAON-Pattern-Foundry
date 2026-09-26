"""SNS attention-factor analysis — decompose click surges into reusable production assets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .accumulation_policy import parse_optional_limit
from .sns_trend_analysis import SNSTrendItem, SNSTrendRejected
from .sns_watch import load_sns_targets, structural_signals_from_manifest


def _parse_rank_limit(value: object) -> int | None:
    parsed = parse_optional_limit(value, default=12)
    if parsed is None:
        return None
    return max(1, parsed)

_FORBIDDEN_TEXT = re.compile(r"(http://|https://|@\w|#\w{3,})", re.IGNORECASE)

_ATTENTION_FACTOR_KEYS = frozenset(
    {
        "primary_driver",
        "secondary_drivers",
        "hook_window_bin",
        "curiosity_mechanism",
        "trust_mechanism",
        "pacing_bin",
        "caption_role",
        "audio_cue_tag",
        "pattern_interrupt",
        "cta_timing_bin",
        "visual_contrast_bin",
        "social_proof_frame",
    }
)

_ALLOWED_HOOK_WINDOWS = frozenset({"0-1s", "0-3s", "3-5s", "late-reveal", "unknown"})
_ALLOWED_PACING = frozenset({"fast-cut", "slow-build", "beat-sync", "static-hold", "unknown"})
_ALLOWED_CTA_TIMING = frozenset({"open", "mid-roll", "end-card", "throughout", "unknown"})

_ANGLE_HEURISTICS: dict[str, dict[str, object]] = {
    "scarcity-countdown": {
        "primary_driver": "scarcity-framing",
        "secondary_drivers": ["countdown-visual", "urgency-copy-digest"],
        "hook_window_bin": "0-1s",
        "curiosity_mechanism": "open-loop",
        "trust_mechanism": "limited-stock-badge",
        "pacing_bin": "fast-cut",
        "caption_role": "headline-overlay",
        "audio_cue_tag": "tick-or-beat",
        "pattern_interrupt": "sudden-zoom",
        "cta_timing_bin": "open",
        "visual_contrast_bin": "high-motion-open",
        "social_proof_frame": "sold-out-digest",
    },
    "restock-alert": {
        "primary_driver": "availability-framing",
        "secondary_drivers": ["notification-style", "badge-flash"],
        "hook_window_bin": "0-3s",
        "curiosity_mechanism": "status-reveal",
        "trust_mechanism": "restock-badge",
        "pacing_bin": "slow-build",
        "caption_role": "alert-banner",
        "audio_cue_tag": "notification-chime",
        "pattern_interrupt": "badge-pop",
        "cta_timing_bin": "mid-roll",
        "visual_contrast_bin": "color-flash",
        "social_proof_frame": "waitlist-digest",
    },
    "time-boxed-offer": {
        "primary_driver": "time-scarcity",
        "secondary_drivers": ["clock-overlay", "price-anchor-digest"],
        "hook_window_bin": "0-1s",
        "curiosity_mechanism": "deadline-pressure",
        "trust_mechanism": "price-comparison-digest",
        "pacing_bin": "fast-cut",
        "caption_role": "offer-headline",
        "audio_cue_tag": "urgency-bed",
        "pattern_interrupt": "timer-snap",
        "cta_timing_bin": "open",
        "visual_contrast_bin": "product-hero",
        "social_proof_frame": "order-volume-bin",
    },
    "beat-sync-hook": {
        "primary_driver": "motion-contrast-open",
        "secondary_drivers": ["template-preview", "transition-flash"],
        "hook_window_bin": "0-1s",
        "curiosity_mechanism": "pattern-preview",
        "trust_mechanism": "tool-capability-digest",
        "pacing_bin": "beat-sync",
        "caption_role": "minimal-hook-text",
        "audio_cue_tag": "beat-drop",
        "pattern_interrupt": "hard-cut",
        "cta_timing_bin": "end-card",
        "visual_contrast_bin": "before-after-split",
        "social_proof_frame": "creator-adoption-bin",
    },
}


class SNSAttentionRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SNSAttentionPolicy:
    enabled: bool = True
    require_attention_factors_for_surge: bool = False
    emit_production_assets: bool = True
    emit_inbox_packets: bool = True
    aggregate_driver_rank_limit: int | None = 12
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> SNSAttentionPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.sns-attention/v1":
            raise SNSAttentionRejected("POLICY_SCHEMA", "unsupported sns attention schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise SNSAttentionRejected("POLICY_FORBIDDEN", "sns attention must remain proposal-only")
        return cls(
            enabled=bool(document.get("enabled", True)),
            require_attention_factors_for_surge=bool(document.get("require_attention_factors_for_surge", False)),
            emit_production_assets=bool(document.get("emit_production_assets", True)),
            emit_inbox_packets=bool(document.get("emit_inbox_packets", True)),
            aggregate_driver_rank_limit=_parse_rank_limit(document.get("aggregate_driver_rank_limit", 12)),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
        )


def _validate_tag(value: str, *, field: str) -> str:
    cleaned = value.strip()
    if not cleaned or _FORBIDDEN_TEXT.search(cleaned):
        raise SNSAttentionRejected("TAG_INVALID", f"{field} must be abstract tag without URLs/handles")
    return cleaned


def normalize_attention_factors(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise SNSAttentionRejected("ATTENTION_SHAPE", "attention_factors must be an object")
    extra = set(raw) - _ATTENTION_FACTOR_KEYS
    if extra:
        raise SNSAttentionRejected("ATTENTION_KEYS", f"attention_factors contains disallowed keys: {sorted(extra)}")
    primary = _validate_tag(str(raw.get("primary_driver", "")).strip(), field="primary_driver")
    if not primary:
        raise SNSAttentionRejected("ATTENTION_PRIMARY", "primary_driver is required")
    secondary_raw = raw.get("secondary_drivers") or ()
    if not isinstance(secondary_raw, (list, tuple)):
        raise SNSAttentionRejected("ATTENTION_SECONDARY", "secondary_drivers must be a list")
    secondary = tuple(_validate_tag(str(item), field="secondary_drivers") for item in secondary_raw if str(item).strip())
    hook_window = str(raw.get("hook_window_bin", "unknown")).strip() or "unknown"
    if hook_window not in _ALLOWED_HOOK_WINDOWS:
        raise SNSAttentionRejected("HOOK_WINDOW", f"unsupported hook_window_bin: {hook_window}")
    pacing = str(raw.get("pacing_bin", "unknown")).strip() or "unknown"
    if pacing not in _ALLOWED_PACING:
        raise SNSAttentionRejected("PACING_BIN", f"unsupported pacing_bin: {pacing}")
    cta_timing = str(raw.get("cta_timing_bin", "unknown")).strip() or "unknown"
    if cta_timing not in _ALLOWED_CTA_TIMING:
        raise SNSAttentionRejected("CTA_TIMING", f"unsupported cta_timing_bin: {cta_timing}")
    optional_fields = (
        "curiosity_mechanism",
        "trust_mechanism",
        "caption_role",
        "audio_cue_tag",
        "pattern_interrupt",
        "visual_contrast_bin",
        "social_proof_frame",
    )
    document: dict[str, object] = {
        "primary_driver": primary,
        "secondary_drivers": list(secondary),
        "hook_window_bin": hook_window,
        "pacing_bin": pacing,
        "cta_timing_bin": cta_timing,
    }
    for field in optional_fields:
        if field in raw:
            document[field] = _validate_tag(str(raw[field]), field=field)
    return document


def infer_attention_factors(*, content_angle_tag: str) -> dict[str, object]:
    heuristic = _ANGLE_HEURISTICS.get(content_angle_tag)
    if not heuristic:
        return {
            "primary_driver": "unknown-attention-driver",
            "secondary_drivers": [],
            "hook_window_bin": "unknown",
            "pacing_bin": "unknown",
            "cta_timing_bin": "unknown",
        }
    return dict(heuristic)


@dataclass(frozen=True)
class AttentionProductionAsset:
    asset_id: str
    platform_id: str
    watch_id: str
    item_id: str
    category_tag: str
    content_angle_tag: str
    click_velocity_bin: str
    attention_factors: dict[str, object]
    factor_source: str
    production_guidance: str
    reuse_domains: tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.shorts-production-asset/v1",
            "asset_id": self.asset_id,
            "platform_id": self.platform_id,
            "watch_id": self.watch_id,
            "item_id": self.item_id,
            "category_tag": self.category_tag,
            "content_angle_tag": self.content_angle_tag,
            "click_velocity_bin": self.click_velocity_bin,
            "attention_factors": self.attention_factors,
            "factor_source": self.factor_source,
            "production_guidance": self.production_guidance,
            "reuse_domains": list(self.reuse_domains),
            "verbatim_post_storage": False,
            "production_change_allowed": False,
            "automatic_learning": False,
        }


@dataclass(frozen=True)
class SNSAttentionReport:
    foundry_root: Path
    evaluated_at: datetime
    assets: tuple[AttentionProductionAsset, ...]
    driver_rankings: tuple[tuple[str, int], ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.sns-attention-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "asset_count": len(self.assets),
            "report_digest": self.report_digest,
            "driver_rankings": [{"driver": driver, "count": count} for driver, count in self.driver_rankings],
            "assets": [asset.to_document() for asset in self.assets],
            "production_change_allowed": False,
            "automatic_learning": False,
        }


def _reuse_domains(category_tag: str) -> tuple[str, ...]:
    mapping = {
        "commerce-hype": ("VIDEO_TEMPLATE_EFFECTS", "SIGNATURE_MOTION"),
        "food-commerce": ("VIDEO_TEMPLATE_EFFECTS", "SIGNATURE_MOTION"),
        "video-template": ("VIDEO_TEMPLATE_EFFECTS", "SIGNATURE_MOTION", "CAPCUT_STYLE_BRIDGE"),
        "creator-tool": ("VIDEO_TEMPLATE_EFFECTS", "LANDING_COPY_PATTERNS"),
    }
    return mapping.get(category_tag, ("VIDEO_TEMPLATE_EFFECTS",))


def _build_production_guidance(factors: dict[str, object]) -> str:
    primary = factors.get("primary_driver", "unknown")
    hook = factors.get("hook_window_bin", "unknown")
    pacing = factors.get("pacing_bin", "unknown")
    curiosity = factors.get("curiosity_mechanism")
    secondary = factors.get("secondary_drivers") or []
    secondary_text = ", ".join(str(item) for item in secondary[:3]) if secondary else "none"
    parts = [
        f"Lead with '{primary}' inside hook window {hook}.",
        f"Pacing: {pacing}; secondary drivers: {secondary_text}.",
    ]
    if curiosity:
        parts.append(f"Curiosity mechanism: {curiosity}.")
    cta = factors.get("cta_timing_bin")
    if cta and cta != "unknown":
        parts.append(f"Place CTA emphasis at {cta}.")
    return " ".join(parts)


def _load_attention_by_item(manifest_path: Path) -> dict[str, dict[str, object]]:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    signals = document.get("observation_signals") or {}
    if not isinstance(signals, dict):
        return {}
    mapping: dict[str, dict[str, object]] = {}
    for raw in signals.get("trend_items") or ():
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id", "")).strip()
        if not item_id:
            continue
        if "attention_factors" in raw:
            mapping[item_id] = normalize_attention_factors(raw["attention_factors"])
    return mapping


class SNSAttentionAnalyzer:
    def __init__(self, *, foundry_root: Path, policy: SNSAttentionPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-sns-attention.json"
        self.policy = policy or SNSAttentionPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "sns-attention"
        self.asset_root = self.foundry_root / "knowledge" / "shorts-production-assets"
        self.store_root.mkdir(parents=True, exist_ok=True)
        if self.policy.emit_production_assets:
            self.asset_root.mkdir(parents=True, exist_ok=True)

    def analyze_surge_items(
        self,
        *,
        surge_items: tuple[SNSTrendItem, ...],
        now: datetime,
    ) -> SNSAttentionReport:
        if now.tzinfo is None:
            raise SNSAttentionRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled or not surge_items:
            return self._empty_report(now=now)

        manifest_by_watch: dict[str, Path] = {}
        for target in load_sns_targets(self.foundry_root):
            if not target.enabled or not target.path:
                continue
            manifest = self.foundry_root / target.path
            if manifest.is_file():
                manifest_by_watch[target.watch_id] = manifest

        assets: list[AttentionProductionAsset] = []
        driver_counts: dict[str, int] = {}

        for item in surge_items:
            manifest = manifest_by_watch.get(item.watch_id)
            factors: dict[str, object] | None = None
            factor_source = "angle-heuristic"
            if manifest and manifest.is_file():
                try:
                    structural_signals_from_manifest(json.loads(manifest.read_text(encoding="utf-8")))
                    attention_map = _load_attention_by_item(manifest)
                    factors = attention_map.get(item.item_id)
                    if factors:
                        factor_source = "manifest"
                except (SNSAttentionRejected, SNSTrendRejected, json.JSONDecodeError, OSError):
                    factors = None
            if factors is None:
                if self.policy.require_attention_factors_for_surge:
                    continue
                factors = infer_attention_factors(content_angle_tag=item.content_angle_tag)
            primary = str(factors.get("primary_driver", "unknown"))
            driver_counts[primary] = driver_counts.get(primary, 0) + 1
            for secondary in factors.get("secondary_drivers") or ():
                key = str(secondary)
                driver_counts[key] = driver_counts.get(key, 0) + 1

            asset_id = sha256(
                f"{item.platform_id}|{item.watch_id}|{item.item_id}|{primary}|{factor_source}".encode()
            ).hexdigest()[:16]
            asset = AttentionProductionAsset(
                asset_id=asset_id,
                platform_id=item.platform_id,
                watch_id=item.watch_id,
                item_id=item.item_id,
                category_tag=item.category_tag,
                content_angle_tag=item.content_angle_tag,
                click_velocity_bin=item.click_velocity_bin,
                attention_factors=factors,
                factor_source=factor_source,
                production_guidance=_build_production_guidance(factors),
                reuse_domains=_reuse_domains(item.category_tag),
            )
            assets.append(asset)
            if self.policy.emit_production_assets:
                asset_path = self.asset_root / f"{item.platform_id.lower()}-{item.item_id}.json"
                asset_path.write_text(
                    json.dumps(asset.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

        ranked_all = sorted(driver_counts.items(), key=lambda row: (-row[1], row[0]))
        if self.policy.aggregate_driver_rank_limit is None:
            ranked = tuple(ranked_all)
        else:
            ranked = tuple(ranked_all[: self.policy.aggregate_driver_rank_limit])
        digest_payload = {
            "evaluated_at": now.isoformat(),
            "asset_count": len(assets),
            "top_driver": ranked[0][0] if ranked else None,
        }
        digest = sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
        report = SNSAttentionReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            assets=tuple(assets),
            driver_rankings=ranked,
            report_digest=digest,
        )
        dated = self.store_root / f"{now.strftime('%Y-%m-%d')}-{digest[:12]}.json"
        dated.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        latest = self.store_root / "latest.json"
        latest.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def _empty_report(self, *, now: datetime) -> SNSAttentionReport:
        digest = sha256(now.isoformat().encode()).hexdigest()
        return SNSAttentionReport(self.foundry_root, now, (), (), digest)
