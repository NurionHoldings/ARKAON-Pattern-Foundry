"""Detect missing feature Intent_DNA after Beom/Eternian additions; authorized Pass-0 self-generation."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .domain import CRITICAL_AXES, INTENT_AXES


class IntentDnaSelfRepairRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FeatureContributor(str, Enum):
    BEOM = "BEOM"
    ETERNIAN = "ETERNIAN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IntentDnaSelfRepairPolicy:
    enabled: bool = True
    self_generation_allowed: bool = True
    mutate_locked_intent_dna: bool = False
    scan_feature_configs: bool = True
    scan_inbox_packets: bool = True
    minimum_completeness: float = 0.85
    emit_research_packet: bool = True
    emit_eternian_packet: bool = True
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> IntentDnaSelfRepairPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.intent-dna-self-repair/v1":
            raise IntentDnaSelfRepairRejected("POLICY_SCHEMA", "unsupported intent dna self-repair schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise IntentDnaSelfRepairRejected("POLICY_FORBIDDEN", "intent dna self-repair must remain propose-only")
        if document.get("mutate_locked_intent_dna"):
            raise IntentDnaSelfRepairRejected("POLICY_FORBIDDEN", "locked intent dna mutation is never allowed here")
        return cls(
            enabled=bool(document.get("enabled", True)),
            self_generation_allowed=bool(document.get("self_generation_allowed", True)),
            mutate_locked_intent_dna=bool(document.get("mutate_locked_intent_dna")),
            scan_feature_configs=bool(document.get("scan_feature_configs", True)),
            scan_inbox_packets=bool(document.get("scan_inbox_packets", True)),
            minimum_completeness=float(document.get("minimum_completeness", 0.85)),
            emit_research_packet=bool(document.get("emit_research_packet", True)),
            emit_eternian_packet=bool(document.get("emit_eternian_packet", True)),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
        )


@dataclass(frozen=True)
class MissingIntentFeature:
    feature_id: str
    contributor: FeatureContributor
    evidence_refs: tuple[str, ...]
    reason: str
    completeness: float | None = None

    def to_document(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "contributor": self.contributor.value,
            "reason": self.reason,
            "completeness": self.completeness,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class GeneratedIntentSeed:
    feature_id: str
    contributor: FeatureContributor
    seed_path: str
    fingerprint: str
    completeness: float
    pass_stage: int

    def to_document(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "contributor": self.contributor.value,
            "seed_path": self.seed_path,
            "fingerprint": self.fingerprint,
            "completeness": self.completeness,
            "pass_stage": self.pass_stage,
        }


@dataclass(frozen=True)
class IntentDnaSelfRepairReport:
    foundry_root: Path
    evaluated_at: datetime
    missing_features: tuple[MissingIntentFeature, ...]
    generated_seeds: tuple[GeneratedIntentSeed, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.intent-dna-self-repair-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "missing_count": len(self.missing_features),
            "generated_count": len(self.generated_seeds),
            "report_digest": self.report_digest,
            "missing_features": [item.to_document() for item in self.missing_features],
            "generated_seeds": [item.to_document() for item in self.generated_seeds],
            "automatic_implement_allowed": False,
            "production_change_allowed": False,
        }


def _slug_from_config(path: Path) -> str:
    name = path.name.removeprefix("arkaon-").removesuffix(".json")
    return name


def _module_path_for_feature(foundry_root: Path, feature_id: str) -> Path | None:
    module_name = feature_id.replace("-", "_")
    candidate = foundry_root / "src" / "apf" / f"{module_name}.py"
    return candidate if candidate.is_file() else None


def _doc_title_for_feature(foundry_root: Path, feature_id: str) -> str | None:
    docs_root = foundry_root / "docs"
    if not docs_root.is_dir():
        return None
    token = feature_id.replace("-", " ")
    for path in sorted(docs_root.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        first_line = text.splitlines()[0] if text else ""
        if feature_id in path.name or token in first_line.lower():
            return first_line.lstrip("# ").strip() or path.stem
    return None


def _module_summary(module_path: Path) -> str | None:
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    doc = ast.get_docstring(tree)
    if not doc:
        return None
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _infer_contributor(*, module_path: Path | None, config_document: dict[str, object]) -> FeatureContributor:
    haystack = json.dumps(config_document, ensure_ascii=False).lower()
    if module_path and module_path.is_file():
        haystack += module_path.read_text(encoding="utf-8", errors="ignore").lower()
    if "eternian" in haystack:
        return FeatureContributor.ETERNIAN
    if "beom" in haystack or "operator" in haystack:
        return FeatureContributor.BEOM
    return FeatureContributor.UNKNOWN


def _axis_values_from_text(*, feature_id: str, title: str, summary: str, notes: tuple[str, ...]) -> dict[str, list[str]]:
    note_text = "; ".join(notes[:3]) if notes else summary
    return {
        "why": [f"{title}: {summary}"],
        "who": ["범(운영자)", "에테르니언 검토자", "아르카온 자가진단"],
        "value": [f"{feature_id} 기능의 의도·경계를 기계 판독 가능하게 고정"],
        "outcome": ["Pass-0 Intent_DNA seed 생성", "에테르니언 검토 후 CORE lock 가능"],
        "journey": ["기능 추가 → intent 누락 감지 → Pass-0 seed 자가생성 → inbox 검토"],
        "object": [feature_id.replace("-", " ")],
        "owner": ["누리온 Foundry 거버넌스", "에테르니언 최종 lock 권한"],
        "invariant": ["locked Intent_DNA mutation 금지", "propose-only inbox 유지"],
        "constraint": [note_text or "자동 배포·production change 금지"],
        "risk": ["의도 누락 시 학습·승격 경로 단절", "잘못된 seed는 eternian review에서 차단"],
        "signal": ["missing_intent_count", "generated_seed_count", "completeness"],
        "evolution": ["Pass 1 evidence routing", "Pass 3 human lock"],
    }


def _completeness_for_axes(axes: dict[str, list[str]]) -> float:
    present = sum(1 for axis in INTENT_AXES if axes.get(axis))
    critical_present = sum(1 for axis in CRITICAL_AXES if axes.get(axis))
    if not present:
        return 0.0
    base = present / len(INTENT_AXES)
    critical_bonus = 0.0 if critical_present == len(CRITICAL_AXES) else -0.1
    return round(max(0.0, min(1.0, base + critical_bonus)), 4)


def _fingerprint_seed(document: dict[str, object]) -> str:
    payload = {
        "feature_id": document.get("feature_id"),
        "feature_intent": document.get("feature_intent"),
        "pass_stage": document.get("pass_stage"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _load_feature_seed(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if document.get("schema_version") != "apf.feature-intent-seed/v1":
        return None
    return document


def _scan_feature_configs(foundry_root: Path, *, minimum_completeness: float) -> list[MissingIntentFeature]:
    config_dir = foundry_root / "config"
    if not config_dir.is_dir():
        return []
    missing: list[MissingIntentFeature] = []
    seeds_dir = foundry_root / "knowledge" / "feature-intents"
    for config_path in sorted(config_dir.glob("arkaon-*.json")):
        feature_id = _slug_from_config(config_path)
        if feature_id in {"predeployment-readiness", "accumulation-policy", "intent-dna-self-repair"}:
            continue
        try:
            config_document = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        seed_path = seeds_dir / f"{feature_id}.json"
        seed = _load_feature_seed(seed_path)
        module_path = _module_path_for_feature(foundry_root, feature_id)
        contributor = _infer_contributor(module_path=module_path, config_document=config_document)
        evidence = tuple(
            ref
            for ref in (
                config_path.relative_to(foundry_root).as_posix(),
                module_path.relative_to(foundry_root).as_posix() if module_path else None,
            )
            if ref
        )
        if seed is None:
            missing.append(
                MissingIntentFeature(
                    feature_id=feature_id,
                    contributor=contributor,
                    evidence_refs=evidence,
                    reason="FEATURE_INTENT_SEED_MISSING",
                )
            )
            continue
        completeness = float(seed.get("completeness", 0.0))
        if seed.get("gates", {}).get("locked") and completeness < minimum_completeness:
            missing.append(
                MissingIntentFeature(
                    feature_id=feature_id,
                    contributor=contributor,
                    evidence_refs=evidence + (seed_path.relative_to(foundry_root).as_posix(),),
                    reason="LOCKED_INTENT_INCOMPLETE",
                    completeness=completeness,
                )
            )
        elif completeness < minimum_completeness:
            missing.append(
                MissingIntentFeature(
                    feature_id=feature_id,
                    contributor=contributor,
                    evidence_refs=evidence + (seed_path.relative_to(foundry_root).as_posix(),),
                    reason="INTENT_COMPLETENESS_BELOW_THRESHOLD",
                    completeness=completeness,
                )
            )
    return missing


def _scan_inbox_packets(foundry_root: Path) -> list[MissingIntentFeature]:
    inbox_root = foundry_root / "inbox"
    if not inbox_root.is_dir():
        return []
    missing: list[MissingIntentFeature] = []
    for stage in ("operator-decision", "eternian-review", "self-improvement"):
        stage_dir = inbox_root / stage
        if not stage_dir.is_dir():
            continue
        for path in sorted(stage_dir.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if document.get("intent_dna") or document.get("feature_intent"):
                continue
            packet_kind = str(document.get("packet_kind", ""))
            if packet_kind in {"LEARNING_MODIFICATION_REQUEST", "INTENT_DNA_SELF_REPAIR"}:
                continue
            assignee = str(document.get("assignee", "")).lower()
            contributor = FeatureContributor.BEOM if assignee == "beom" else FeatureContributor.ETERNIAN
            if stage == "eternian-review":
                contributor = FeatureContributor.ETERNIAN
            feature_id = str(document.get("platform_id") or document.get("packet_id") or path.stem)
            missing.append(
                MissingIntentFeature(
                    feature_id=feature_id,
                    contributor=contributor,
                    evidence_refs=(path.relative_to(foundry_root).as_posix(),),
                    reason="INBOX_PACKET_INTENT_DNA_MISSING",
                )
            )
    return missing


def build_pass0_seed_document(
    *,
    feature_id: str,
    contributor: FeatureContributor,
    foundry_root: Path,
    config_path: Path,
) -> dict[str, object]:
    config_document = json.loads(config_path.read_text(encoding="utf-8"))
    module_path = _module_path_for_feature(foundry_root, feature_id)
    summary = _module_summary(module_path) if module_path else f"ARKAON feature {feature_id}"
    title = _doc_title_for_feature(foundry_root, feature_id) or feature_id.replace("-", " ").title()
    notes = tuple(str(item) for item in (config_document.get("notes") or ())[:5])
    axes = _axis_values_from_text(feature_id=feature_id, title=title, summary=summary or title, notes=notes)
    completeness = _completeness_for_axes(axes)
    document: dict[str, object] = {
        "schema_version": "apf.feature-intent-seed/v1",
        "feature_id": feature_id,
        "contributor": contributor.value,
        "pass_stage": 0,
        "phase": "PASS0_SELF_GENERATED",
        "authorization": {
            "basis": "SELF_DIAGNOSIS_SELF_GENERATION",
            "scope": "MISSING_INTENT_DNA_ONLY",
            "mutate_locked_intent_dna": False,
        },
        "feature_intent": axes,
        "completeness": completeness,
        "evidence_refs": [
            config_path.relative_to(foundry_root).as_posix(),
            *( [module_path.relative_to(foundry_root).as_posix()] if module_path else [] ),
        ],
        "gates": {
            "intent_dna_mutation": False,
            "locked": False,
            "review_status": "ETERNIAN_REVIEW_REQUIRED",
        },
    }
    document["fingerprint"] = _fingerprint_seed(document)
    return document


def generate_pass0_seed(
    *,
    foundry_root: Path,
    feature: MissingIntentFeature,
    dry_run: bool,
) -> GeneratedIntentSeed | None:
    if feature.reason == "INBOX_PACKET_INTENT_DNA_MISSING":
        return None
    config_path = foundry_root / "config" / f"arkaon-{feature.feature_id}.json"
    if not config_path.is_file():
        return None
    document = build_pass0_seed_document(
        feature_id=feature.feature_id,
        contributor=feature.contributor,
        foundry_root=foundry_root,
        config_path=config_path,
    )
    seeds_dir = foundry_root / "knowledge" / "feature-intents"
    target = seeds_dir / f"{feature.feature_id}.json"
    if not dry_run:
        seeds_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return GeneratedIntentSeed(
        feature_id=feature.feature_id,
        contributor=feature.contributor,
        seed_path=target.relative_to(foundry_root).as_posix(),
        fingerprint=str(document["fingerprint"]),
        completeness=float(document["completeness"]),
        pass_stage=0,
    )


class IntentDnaSelfRepairEngine:
    def __init__(self, *, foundry_root: Path, policy: IntentDnaSelfRepairPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-intent-dna-self-repair.json"
        self.policy = policy or IntentDnaSelfRepairPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "intent-dna-self-repair"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def analyze(self, *, now: datetime, dry_run: bool = False) -> IntentDnaSelfRepairReport:
        if now.tzinfo is None:
            raise IntentDnaSelfRepairRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            return self._empty_report(now=now)
        missing: list[MissingIntentFeature] = []
        if self.policy.scan_feature_configs:
            missing.extend(
                _scan_feature_configs(self.foundry_root, minimum_completeness=self.policy.minimum_completeness)
            )
        if self.policy.scan_inbox_packets:
            inbox_missing = _scan_inbox_packets(self.foundry_root)
            seen = {item.feature_id for item in missing}
            missing.extend(item for item in inbox_missing if item.feature_id not in seen)
        generated: list[GeneratedIntentSeed] = []
        if self.policy.self_generation_allowed:
            for feature in missing:
                seed = generate_pass0_seed(foundry_root=self.foundry_root, feature=feature, dry_run=dry_run)
                if seed is not None:
                    generated.append(seed)
        digest_payload = {
            "evaluated_at": now.isoformat(),
            "missing_count": len(missing),
            "generated_count": len(generated),
            "feature_ids": sorted({item.feature_id for item in missing}),
        }
        digest = sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
        report = IntentDnaSelfRepairReport(
            foundry_root=self.foundry_root,
            evaluated_at=now,
            missing_features=tuple(missing),
            generated_seeds=tuple(generated),
            report_digest=digest,
        )
        if not dry_run:
            dated = self.store_root / f"{now.strftime('%Y-%m-%d')}-{digest[:12]}.json"
            dated.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            latest = self.store_root / "latest.json"
            latest.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return report

    def _empty_report(self, *, now: datetime) -> IntentDnaSelfRepairReport:
        digest = sha256(now.isoformat().encode()).hexdigest()
        return IntentDnaSelfRepairReport(self.foundry_root, now, (), (), digest)
