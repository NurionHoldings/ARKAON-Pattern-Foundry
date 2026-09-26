"""Proposal quality score — learning assets weighted toward better co-creation proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path


class ProposalQualityRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProposalQualityPolicy:
    enabled: bool = True
    minimum_proposal_quality_score: float = 0.2
    weight_landing_patterns: float = 0.4
    weight_cross_platform_learning: float = 0.3
    weight_reflective_lessons: float = 0.2
    weight_self_evolution_analyses: float = 0.1
    full_score_landing_patterns: int = 3
    full_score_cross_platform_learning: int = 3
    full_score_reflective_lessons: int = 2
    full_score_self_evolution_analyses: int = 1

    @classmethod
    def load(cls, path: Path) -> ProposalQualityPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.proposal-quality/v1":
            raise ProposalQualityRejected("POLICY_SCHEMA", "unsupported proposal quality schema")
        return cls(
            enabled=bool(document.get("enabled", True)),
            minimum_proposal_quality_score=float(document.get("minimum_proposal_quality_score", 0.2)),
            weight_landing_patterns=float(document.get("weight_landing_patterns", 0.4)),
            weight_cross_platform_learning=float(document.get("weight_cross_platform_learning", 0.3)),
            weight_reflective_lessons=float(document.get("weight_reflective_lessons", 0.2)),
            weight_self_evolution_analyses=float(document.get("weight_self_evolution_analyses", 0.1)),
            full_score_landing_patterns=max(1, int(document.get("full_score_landing_patterns", 3))),
            full_score_cross_platform_learning=max(
                1, int(document.get("full_score_cross_platform_learning", 3))
            ),
            full_score_reflective_lessons=max(1, int(document.get("full_score_reflective_lessons", 2))),
            full_score_self_evolution_analyses=max(
                1, int(document.get("full_score_self_evolution_analyses", 1))
            ),
        )


@dataclass(frozen=True)
class ProposalQualityBreakdown:
    landing_patterns: int
    cross_platform_learning: int
    reflective_lessons: int
    self_evolution_analyses: int
    landing_patterns_component: float
    cross_platform_learning_component: float
    reflective_lessons_component: float
    self_evolution_analyses_component: float

    def to_document(self) -> dict[str, object]:
        return {
            "landing_patterns": self.landing_patterns,
            "cross_platform_learning": self.cross_platform_learning,
            "reflective_lessons": self.reflective_lessons,
            "self_evolution_analyses": self.self_evolution_analyses,
            "landing_patterns_component": round(self.landing_patterns_component, 4),
            "cross_platform_learning_component": round(self.cross_platform_learning_component, 4),
            "reflective_lessons_component": round(self.reflective_lessons_component, 4),
            "self_evolution_analyses_component": round(self.self_evolution_analyses_component, 4),
        }


@dataclass(frozen=True)
class ProposalQualityReport:
    score: float
    minimum_required: float
    gate_pass: bool
    artifact_count: int
    breakdown: ProposalQualityBreakdown
    north_star: str
    report_digest: str
    evaluated_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.proposal-quality-report/v1",
            "score": round(self.score, 4),
            "minimum_required": self.minimum_required,
            "gate_pass": self.gate_pass,
            "artifact_count": self.artifact_count,
            "breakdown": self.breakdown.to_document(),
            "north_star": self.north_star,
            "report_digest": self.report_digest,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


_NORTH_STAR = "모든 학습 자산은 더 나은 제안을 하기 위함이다."


def _count_artifacts(foundry_root: Path) -> ProposalQualityBreakdown:
    patterns_dir = foundry_root / "knowledge" / "landing-structure-patterns" / "proposed"
    learning_dir = foundry_root / "state" / "cross-platform-learning"
    lessons_dir = foundry_root / "knowledge" / "reflective-lessons"
    analyses_dir = foundry_root / "state" / "self-evolution" / "analyses"
    landing_patterns = len(list(patterns_dir.glob("*.json"))) if patterns_dir.is_dir() else 0
    cross_platform_learning = len(list(learning_dir.glob("20*.json"))) if learning_dir.is_dir() else 0
    reflective_lessons = len(list(lessons_dir.glob("*.json"))) if lessons_dir.is_dir() else 0
    self_evolution_analyses = len(list(analyses_dir.glob("*.json"))) if analyses_dir.is_dir() else 0
    return ProposalQualityBreakdown(
        landing_patterns=landing_patterns,
        cross_platform_learning=cross_platform_learning,
        reflective_lessons=reflective_lessons,
        self_evolution_analyses=self_evolution_analyses,
        landing_patterns_component=0.0,
        cross_platform_learning_component=0.0,
        reflective_lessons_component=0.0,
        self_evolution_analyses_component=0.0,
    )


def _component_ratio(count: int, full_at: int) -> float:
    return min(count / full_at, 1.0)


class ProposalQualityScorer:
    def __init__(self, *, foundry_root: Path, policy: ProposalQualityPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-proposal-quality.json"
        self.policy = policy or ProposalQualityPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "proposal-quality"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def evaluate(self, *, now: datetime) -> ProposalQualityReport:
        if now.tzinfo is None:
            raise ProposalQualityRejected("TIMESTAMP", "timezone-aware timestamp required")
        raw = _count_artifacts(self.foundry_root)
        policy = self.policy
        landing_component = _component_ratio(raw.landing_patterns, policy.full_score_landing_patterns)
        learning_component = _component_ratio(
            raw.cross_platform_learning, policy.full_score_cross_platform_learning
        )
        lessons_component = _component_ratio(raw.reflective_lessons, policy.full_score_reflective_lessons)
        analyses_component = _component_ratio(
            raw.self_evolution_analyses, policy.full_score_self_evolution_analyses
        )
        score = (
            policy.weight_landing_patterns * landing_component
            + policy.weight_cross_platform_learning * learning_component
            + policy.weight_reflective_lessons * lessons_component
            + policy.weight_self_evolution_analyses * analyses_component
        )
        breakdown = ProposalQualityBreakdown(
            landing_patterns=raw.landing_patterns,
            cross_platform_learning=raw.cross_platform_learning,
            reflective_lessons=raw.reflective_lessons,
            self_evolution_analyses=raw.self_evolution_analyses,
            landing_patterns_component=policy.weight_landing_patterns * landing_component,
            cross_platform_learning_component=policy.weight_cross_platform_learning * learning_component,
            reflective_lessons_component=policy.weight_reflective_lessons * lessons_component,
            self_evolution_analyses_component=policy.weight_self_evolution_analyses * analyses_component,
        )
        artifact_count = (
            breakdown.landing_patterns
            + breakdown.cross_platform_learning
            + breakdown.reflective_lessons
            + breakdown.self_evolution_analyses
        )
        minimum = policy.minimum_proposal_quality_score if policy.enabled else 0.0
        gate_pass = score >= minimum
        body = {
            "score": round(score, 4),
            "minimum_required": minimum,
            "breakdown": breakdown.to_document(),
        }
        report_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        report = ProposalQualityReport(
            score=score,
            minimum_required=minimum,
            gate_pass=gate_pass,
            artifact_count=artifact_count,
            breakdown=breakdown,
            north_star=_NORTH_STAR,
            report_digest=report_digest,
            evaluated_at=now,
        )
        return report

    def evaluate_and_persist(self, *, now: datetime) -> ProposalQualityReport:
        report = self.evaluate(now=now)
        latest = self.store_root / "latest.json"
        latest.write_text(
            json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        stamped = self.store_root / f"{now.strftime('%Y%m%dT%H%M%S')}-{report.report_digest[:12]}.json"
        stamped.write_text(
            json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report

    def load_latest(self) -> ProposalQualityReport | None:
        path = self.store_root / "latest.json"
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        breakdown_doc = document["breakdown"]
        breakdown = ProposalQualityBreakdown(
            landing_patterns=int(breakdown_doc["landing_patterns"]),
            cross_platform_learning=int(breakdown_doc["cross_platform_learning"]),
            reflective_lessons=int(breakdown_doc["reflective_lessons"]),
            self_evolution_analyses=int(breakdown_doc["self_evolution_analyses"]),
            landing_patterns_component=float(breakdown_doc["landing_patterns_component"]),
            cross_platform_learning_component=float(breakdown_doc["cross_platform_learning_component"]),
            reflective_lessons_component=float(breakdown_doc["reflective_lessons_component"]),
            self_evolution_analyses_component=float(breakdown_doc["self_evolution_analyses_component"]),
        )
        return ProposalQualityReport(
            score=float(document["score"]),
            minimum_required=float(document["minimum_required"]),
            gate_pass=bool(document["gate_pass"]),
            artifact_count=int(document["artifact_count"]),
            breakdown=breakdown,
            north_star=str(document.get("north_star", _NORTH_STAR)),
            report_digest=str(document["report_digest"]),
            evaluated_at=datetime.fromisoformat(str(document["evaluated_at"])),
        )


def count_learning_artifacts(foundry_root: Path) -> int:
    """Count phase-1 learning artifacts that feed proposal quality."""
    breakdown = _count_artifacts(foundry_root)
    return (
        breakdown.landing_patterns
        + breakdown.cross_platform_learning
        + breakdown.reflective_lessons
    )


def assert_proposal_quality_gate(*, foundry_root: Path, minimum_artifacts: int = 1) -> ProposalQualityReport:
    """Fail-closed gate for co-creation: artifacts + weighted quality score."""
    scorer = ProposalQualityScorer(foundry_root=foundry_root)
    now = datetime.now().astimezone()
    report = scorer.evaluate(now=now)
    if count_learning_artifacts(foundry_root) < minimum_artifacts:
        raise ProposalQualityRejected(
            "INSUFFICIENT_EXPERIENCE",
            "phase-1 learning artifacts required before co-creation proposals",
        )
    if scorer.policy.enabled and not report.gate_pass:
        raise ProposalQualityRejected(
            "INSUFFICIENT_PROPOSAL_QUALITY",
            f"proposal quality score {report.score:.3f} below minimum {report.minimum_required:.3f}",
        )
    return report
