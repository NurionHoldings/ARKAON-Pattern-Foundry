"""ARKAON self-evolution snapshots and past-vs-present capability comparison."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path


class SelfEvolutionRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ImprovementContributor(str, Enum):
    BEOM = "BEOM"
    ETERNIAN = "ETERNIAN"
    OPERATOR = "OPERATOR"
    TENANT_FEEDBACK = "TENANT_FEEDBACK"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class SelfEvolutionComparePolicy:
    enabled: bool = True
    snapshot_on_feedback_revision: bool = True
    snapshot_on_deploy_stage: bool = True

    @classmethod
    def load(cls, path: Path) -> SelfEvolutionComparePolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.self-evolution-compare/v1":
            raise SelfEvolutionRejected("POLICY_SCHEMA", "unsupported self-evolution compare schema")
        return cls(
            enabled=bool(document.get("enabled", True)),
            snapshot_on_feedback_revision=bool(document.get("snapshot_on_feedback_revision", True)),
            snapshot_on_deploy_stage=bool(document.get("snapshot_on_deploy_stage", True)),
        )


@dataclass(frozen=True)
class CapabilitySnapshot:
    snapshot_id: str
    contributor: ImprovementContributor
    improvement_ref: str
    improvement_summary: str
    capabilities: tuple[str, ...]
    pipeline_stages: tuple[str, ...]
    config_modules: tuple[str, ...]
    captured_at: datetime
    snapshot_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.self-evolution-snapshot/v1",
            "snapshot_id": self.snapshot_id,
            "contributor": self.contributor.value,
            "improvement_ref": self.improvement_ref,
            "improvement_summary": self.improvement_summary,
            "capabilities": list(self.capabilities),
            "pipeline_stages": list(self.pipeline_stages),
            "config_modules": list(self.config_modules),
            "captured_at": self.captured_at.isoformat(),
            "snapshot_digest": self.snapshot_digest,
        }


@dataclass(frozen=True)
class EvolutionComparisonReport:
    baseline_snapshot_id: str
    candidate_snapshot_id: str
    new_capabilities: tuple[str, ...]
    removed_capabilities: tuple[str, ...]
    new_pipeline_stages: tuple[str, ...]
    improved_summary: str
    comparison_digest: str
    compared_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.self-evolution-comparison/v1",
            "baseline_snapshot_id": self.baseline_snapshot_id,
            "candidate_snapshot_id": self.candidate_snapshot_id,
            "new_capabilities": list(self.new_capabilities),
            "removed_capabilities": list(self.removed_capabilities),
            "new_pipeline_stages": list(self.new_pipeline_stages),
            "improved_summary": self.improved_summary,
            "comparison_digest": self.comparison_digest,
            "compared_at": self.compared_at.isoformat(),
        }


_PIPELINE_MARKERS: tuple[tuple[str, str], ...] = (
    ("co_creation_chat", "src/apf/conversational_co_creation.py"),
    ("co_creation_build", "src/apf/co_creation_build.py"),
    ("co_creation_codegen", "src/apf/co_creation_codegen.py"),
    ("co_creation_preview", "src/apf/co_creation_preview.py"),
    ("co_creation_deploy", "src/apf/co_creation_deploy.py"),
    ("cross_platform_learning", "src/apf/cross_platform_learning.py"),
    ("billing_entitlement", "src/apf/billing_entitlement.py"),
    ("self_evolution_compare", "src/apf/arkaon_self_evolution_compare.py"),
)


def _discover_capabilities(foundry_root: Path) -> tuple[str, ...]:
    intents = foundry_root / "knowledge" / "feature-intents"
    keys: set[str] = set()
    if intents.is_dir():
        for path in intents.glob("*.json"):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            feature_id = document.get("feature_id")
            if feature_id:
                keys.add(str(feature_id))
    for marker, _relative in _PIPELINE_MARKERS:
        if (foundry_root / _relative).is_file():
            keys.add(marker)
    return tuple(sorted(keys))


def _discover_pipeline_stages(foundry_root: Path) -> tuple[str, ...]:
    stages: list[str] = []
    for stage, relative in _PIPELINE_MARKERS:
        if (foundry_root / relative).is_file():
            stages.append(stage)
    return tuple(stages)


def _discover_config_modules(foundry_root: Path) -> tuple[str, ...]:
    config = foundry_root / "config"
    if not config.is_dir():
        return ()
    return tuple(sorted(path.name for path in config.glob("arkaon-*.json")))


class ArkaonSelfEvolutionCompareEngine:
    def __init__(self, *, foundry_root: Path, policy: SelfEvolutionComparePolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-self-evolution-compare.json"
        self.policy = policy or SelfEvolutionComparePolicy.load(config)
        self.snapshot_root = self.foundry_root / "state" / "self-evolution" / "snapshots"
        self.comparison_root = self.foundry_root / "state" / "self-evolution" / "comparisons"
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        self.comparison_root.mkdir(parents=True, exist_ok=True)

    def capture_snapshot(
        self,
        *,
        contributor: ImprovementContributor,
        improvement_ref: str,
        improvement_summary: str,
        now: datetime,
    ) -> CapabilitySnapshot:
        if now.tzinfo is None:
            raise SelfEvolutionRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise SelfEvolutionRejected("DISABLED", "self-evolution compare is disabled")
        capabilities = _discover_capabilities(self.foundry_root)
        pipeline_stages = _discover_pipeline_stages(self.foundry_root)
        config_modules = _discover_config_modules(self.foundry_root)
        body = {
            "contributor": contributor.value,
            "improvement_ref": improvement_ref,
            "capabilities": list(capabilities),
            "pipeline_stages": list(pipeline_stages),
            "config_modules": list(config_modules),
            "captured_at": now.isoformat(),
        }
        snapshot_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        snapshot_id = snapshot_digest[:16]
        snapshot = CapabilitySnapshot(
            snapshot_id=snapshot_id,
            contributor=contributor,
            improvement_ref=improvement_ref,
            improvement_summary=improvement_summary,
            capabilities=capabilities,
            pipeline_stages=pipeline_stages,
            config_modules=config_modules,
            captured_at=now,
            snapshot_digest=snapshot_digest,
        )
        path = self.snapshot_root / f"{now.strftime('%Y%m%dT%H%M%S')}-{snapshot_id}.json"
        path.write_text(
            json.dumps(snapshot.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return snapshot

    def list_snapshots(self, *, limit: int = 20) -> tuple[CapabilitySnapshot, ...]:
        paths = sorted(self.snapshot_root.glob("*.json"), reverse=True)[:limit]
        snapshots: list[CapabilitySnapshot] = []
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            snapshots.append(self._document_to_snapshot(document))
        return tuple(snapshots)

    def _document_to_snapshot(self, document: dict[str, object]) -> CapabilitySnapshot:
        return CapabilitySnapshot(
            snapshot_id=str(document["snapshot_id"]),
            contributor=ImprovementContributor(str(document["contributor"])),
            improvement_ref=str(document["improvement_ref"]),
            improvement_summary=str(document.get("improvement_summary", "")),
            capabilities=tuple(document.get("capabilities") or ()),
            pipeline_stages=tuple(document.get("pipeline_stages") or ()),
            config_modules=tuple(document.get("config_modules") or ()),
            captured_at=datetime.fromisoformat(str(document["captured_at"])),
            snapshot_digest=str(document["snapshot_digest"]),
        )

    def compare(
        self,
        *,
        baseline_snapshot_id: str,
        candidate_snapshot_id: str,
        now: datetime,
    ) -> EvolutionComparisonReport:
        if now.tzinfo is None:
            raise SelfEvolutionRejected("TIMESTAMP", "timezone-aware timestamp required")
        baseline = self._load_snapshot_by_id(baseline_snapshot_id)
        candidate = self._load_snapshot_by_id(candidate_snapshot_id)
        baseline_caps = frozenset(baseline.capabilities)
        candidate_caps = frozenset(candidate.capabilities)
        new_capabilities = tuple(sorted(candidate_caps - baseline_caps))
        removed_capabilities = tuple(sorted(baseline_caps - candidate_caps))
        new_pipeline_stages = tuple(
            sorted(set(candidate.pipeline_stages) - set(baseline.pipeline_stages))
        )
        parts = []
        if new_capabilities:
            parts.append(f"새 capability {len(new_capabilities)}개: {', '.join(new_capabilities[:5])}")
        if new_pipeline_stages:
            parts.append(f"새 pipeline stage: {', '.join(new_pipeline_stages)}")
        if candidate.contributor is ImprovementContributor.BEOM:
            parts.append("BEOM(범) 개선 반영")
        if candidate.contributor is ImprovementContributor.ETERNIAN:
            parts.append("ETERNIAN 감사·보완 반영")
        if not parts:
            parts.append("capability fingerprint 동일 — 세부 품질은 교훈·증거로 추적")
        improved_summary = "; ".join(parts)
        body = {
            "baseline_snapshot_id": baseline.snapshot_id,
            "candidate_snapshot_id": candidate.snapshot_id,
            "new_capabilities": list(new_capabilities),
            "removed_capabilities": list(removed_capabilities),
            "new_pipeline_stages": list(new_pipeline_stages),
            "improved_summary": improved_summary,
        }
        comparison_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        report = EvolutionComparisonReport(
            baseline_snapshot_id=baseline.snapshot_id,
            candidate_snapshot_id=candidate.snapshot_id,
            new_capabilities=new_capabilities,
            removed_capabilities=removed_capabilities,
            new_pipeline_stages=new_pipeline_stages,
            improved_summary=improved_summary,
            comparison_digest=comparison_digest,
            compared_at=now,
        )
        path = self.comparison_root / f"{comparison_digest[:16]}.json"
        document = report.to_document()
        document["improvement_summary"] = candidate.improvement_summary
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def compare_latest_pair(self, *, now: datetime) -> EvolutionComparisonReport:
        snapshots = self.list_snapshots(limit=2)
        if len(snapshots) < 2:
            raise SelfEvolutionRejected("INSUFFICIENT_HISTORY", "at least two snapshots required")
        return self.compare(
            baseline_snapshot_id=snapshots[1].snapshot_id,
            candidate_snapshot_id=snapshots[0].snapshot_id,
            now=now,
        )

    def _load_snapshot_by_id(self, snapshot_id: str) -> CapabilitySnapshot:
        for path in self.snapshot_root.glob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("snapshot_id") == snapshot_id:
                return self._document_to_snapshot(document)
        raise SelfEvolutionRejected("SNAPSHOT_NOT_FOUND", "snapshot not found")
