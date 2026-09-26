"""SNS trend analysis — detect click-surge items and prepare market pioneering proposals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .sns_watch import SNSWatchRejected, load_sns_targets, structural_signals_from_manifest

_ALLOWED_ITEM_KEYS = frozenset(
    {
        "item_id",
        "category_tag",
        "content_angle_tag",
        "click_velocity_bin",
        "engagement_bin",
        "attention_factors",
    }
)
_FORBIDDEN_ITEM_TEXT = re.compile(r"(http://|https://|@\w|#\w{3,})", re.IGNORECASE)


class SNSTrendRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SNSTrendPolicy:
    enabled: bool = True
    surge_velocity_bins: frozenset[str] = frozenset({"surge", "explosive", "very-high"})
    min_surge_items_for_report: int = 1
    emit_market_proposals: bool = True
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> SNSTrendPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.sns-trend/v1":
            raise SNSTrendRejected("POLICY_SCHEMA", "unsupported sns trend schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise SNSTrendRejected("POLICY_FORBIDDEN", "sns trend must remain proposal-only")
        bins = frozenset(str(item) for item in (document.get("surge_velocity_bins") or ()) if str(item).strip())
        return cls(
            enabled=bool(document.get("enabled", True)),
            surge_velocity_bins=bins or frozenset({"surge", "explosive", "very-high"}),
            min_surge_items_for_report=max(1, int(document.get("min_surge_items_for_report", 1))),
            emit_market_proposals=bool(document.get("emit_market_proposals", True)),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
        )


@dataclass(frozen=True)
class SNSTrendItem:
    watch_id: str
    platform_id: str
    item_id: str
    category_tag: str
    content_angle_tag: str
    click_velocity_bin: str
    engagement_bin: str
    is_surge: bool

    def to_document(self) -> dict[str, object]:
        return {
            "watch_id": self.watch_id,
            "platform_id": self.platform_id,
            "item_id": self.item_id,
            "category_tag": self.category_tag,
            "content_angle_tag": self.content_angle_tag,
            "click_velocity_bin": self.click_velocity_bin,
            "engagement_bin": self.engagement_bin,
            "is_surge": self.is_surge,
        }


@dataclass(frozen=True)
class MarketPioneeringProposal:
    proposal_id: str
    platform_id: str
    watch_id: str
    item_id: str
    category_tag: str
    content_angle_tag: str
    click_velocity_bin: str
    suggested_market_scope: str
    user_message: str
    evidence_refs: tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.sns-market-proposal/v1",
            "proposal_id": self.proposal_id,
            "platform_id": self.platform_id,
            "watch_id": self.watch_id,
            "item_id": self.item_id,
            "category_tag": self.category_tag,
            "content_angle_tag": self.content_angle_tag,
            "click_velocity_bin": self.click_velocity_bin,
            "suggested_market_scope": self.suggested_market_scope,
            "user_message": self.user_message,
            "evidence_refs": list(self.evidence_refs),
            "proposal_kind": "MARKET_PIONEERING",
            "production_change_allowed": False,
            "automatic_learning": False,
            "verbatim_post_storage": False,
        }


@dataclass(frozen=True)
class SNSTrendReport:
    foundry_root: Path
    evaluated_at: datetime
    items: tuple[SNSTrendItem, ...]
    surge_items: tuple[SNSTrendItem, ...]
    proposals: tuple[MarketPioneeringProposal, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.sns-trend-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "item_count": len(self.items),
            "surge_count": len(self.surge_items),
            "proposal_count": len(self.proposals),
            "report_digest": self.report_digest,
            "items": [item.to_document() for item in self.items],
            "surge_items": [item.to_document() for item in self.surge_items],
            "proposals": [item.to_document() for item in self.proposals],
            "production_change_allowed": False,
            "automatic_learning": False,
        }


def normalize_trend_item(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    if set(raw) - _ALLOWED_ITEM_KEYS:
        raise SNSTrendRejected("TREND_ITEM_KEYS", "trend item contains disallowed keys")
    item_id = str(raw.get("item_id", "")).strip()
    category_tag = str(raw.get("category_tag", "")).strip()
    content_angle_tag = str(raw.get("content_angle_tag", "")).strip()
    click_velocity_bin = str(raw.get("click_velocity_bin", "unknown")).strip()
    engagement_bin = str(raw.get("engagement_bin", "unknown")).strip()
    for value in (item_id, category_tag, content_angle_tag):
        if not value or _FORBIDDEN_ITEM_TEXT.search(value):
            raise SNSTrendRejected("TREND_ITEM_CONTENT", "trend item must be abstract tags without URLs/handles")
    return {
        "item_id": item_id,
        "category_tag": category_tag,
        "content_angle_tag": content_angle_tag,
        "click_velocity_bin": click_velocity_bin,
        "engagement_bin": engagement_bin,
    }


def _load_trend_items_from_manifest(path: Path) -> tuple[dict[str, str], ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    signals = document.get("observation_signals") or {}
    if not isinstance(signals, dict):
        return ()
    items: list[dict[str, str]] = []
    for raw in signals.get("trend_items") or ():
        normalized = normalize_trend_item(raw)
        if normalized:
            items.append(normalized)
    return tuple(items)


def _suggest_market_scope(category_tag: str, content_angle_tag: str) -> str:
    mapping = {
        "commerce-hype": "DOMESTIC_CREATOR_COMMERCE",
        "food-commerce": "DOMESTIC_FOOD_COMMERCE",
        "creator-tool": "AI_LANDING_COPY_TOOLS",
        "video-template": "SHORT_FORM_VIDEO_TEMPLATES",
    }
    return mapping.get(category_tag, f"EMERGING_{category_tag.upper().replace('-', '_')}")


def _proposal_message(item: SNSTrendItem) -> str:
    return (
        f"SNS에서 '{item.item_id}' ({item.category_tag}/{item.content_angle_tag}) 클릭 속도 "
        f"'{item.click_velocity_bin}' 급등 신호가 관측되었습니다. "
        f"해당 각도의 시장 개척·Intent 정렬을 검토하세요. 자동 배포는 없습니다."
    )


class SNSTrendAnalyzer:
    def __init__(self, *, foundry_root: Path, policy: SNSTrendPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-sns-trend.json"
        self.policy = policy or SNSTrendPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "sns-trend"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def analyze(self, *, now: datetime) -> SNSTrendReport:
        if now.tzinfo is None:
            raise SNSTrendRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            return self._empty_report(now=now)

        items: list[SNSTrendItem] = []
        evidence_by_watch: dict[str, str] = {}
        for target in load_sns_targets(self.foundry_root):
            if not target.enabled or not target.path:
                continue
            manifest = self.foundry_root / target.path
            if not manifest.is_file():
                continue
            try:
                structural_signals_from_manifest(json.loads(manifest.read_text(encoding="utf-8")))
                trend_rows = _load_trend_items_from_manifest(manifest)
            except (SNSWatchRejected, SNSTrendRejected, json.JSONDecodeError, OSError):
                continue
            evidence_by_watch[target.watch_id] = manifest.relative_to(self.foundry_root).as_posix()
            for row in trend_rows:
                velocity = row["click_velocity_bin"]
                is_surge = velocity in self.policy.surge_velocity_bins
                items.append(
                    SNSTrendItem(
                        watch_id=target.watch_id,
                        platform_id=target.platform_id,
                        item_id=row["item_id"],
                        category_tag=row["category_tag"],
                        content_angle_tag=row["content_angle_tag"],
                        click_velocity_bin=velocity,
                        engagement_bin=row["engagement_bin"],
                        is_surge=is_surge,
                    )
                )

        surge_items = tuple(item for item in items if item.is_surge)
        proposals: list[MarketPioneeringProposal] = []
        if self.policy.emit_market_proposals and len(surge_items) >= self.policy.min_surge_items_for_report:
            for item in surge_items:
                proposal_id = sha256(
                    f"{item.platform_id}|{item.watch_id}|{item.item_id}|{item.click_velocity_bin}".encode()
                ).hexdigest()[:16]
                manifest_ref = evidence_by_watch.get(item.watch_id, "config/sns-watch-sources.json")
                proposals.append(
                    MarketPioneeringProposal(
                        proposal_id=proposal_id,
                        platform_id=item.platform_id,
                        watch_id=item.watch_id,
                        item_id=item.item_id,
                        category_tag=item.category_tag,
                        content_angle_tag=item.content_angle_tag,
                        click_velocity_bin=item.click_velocity_bin,
                        suggested_market_scope=_suggest_market_scope(item.category_tag, item.content_angle_tag),
                        user_message=_proposal_message(item),
                        evidence_refs=(manifest_ref, "config/arkaon-sns-trend.json"),
                    )
                )

        document = {
            "evaluated_at": now.isoformat(),
            "surge_count": len(surge_items),
            "proposal_count": len(proposals),
        }
        digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        report = SNSTrendReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            items=tuple(items),
            surge_items=surge_items,
            proposals=tuple(proposals),
            report_digest=digest,
        )
        target = self.store_root / f"{now.strftime('%Y-%m-%d')}-{digest[:12]}.json"
        target.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        latest = self.store_root / "latest.json"
        latest.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def _empty_report(self, *, now: datetime) -> SNSTrendReport:
        digest = sha256(now.isoformat().encode()).hexdigest()
        return SNSTrendReport(self.foundry_root, now, (), (), (), digest)
