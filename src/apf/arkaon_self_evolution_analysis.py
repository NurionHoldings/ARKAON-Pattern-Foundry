"""Analyze improvement process and added features from self-evolution comparisons."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .arkaon_self_evolution_compare import (
    ArkaonSelfEvolutionCompareEngine,
    CapabilitySnapshot,
    EvolutionComparisonReport,
    SelfEvolutionRejected,
)


class SelfEvolutionAnalysisRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_PIPELINE_PROCESS_ORDER: tuple[tuple[str, str], ...] = (
    ("cross_platform_learning", "1단계: cross-platform 학습·경험 축적"),
    ("co_creation_chat", "2단계: 대화형 Co-Creation blueprint 제안"),
    ("co_creation_build", "3단계: operator 승인 후 scaffold"),
    ("reference-url-style", "3단계: URL 참조 feel 추출"),
    ("co_creation_codegen", "4A: variant codegen"),
    ("co_creation_preview", "4B: tenant preview sandbox"),
    ("co_creation_deploy", "4C: staged deploy"),
    ("billing_entitlement", "결제 entitlement 검증"),
    ("self_evolution_compare", "자기 진화 이력·비교"),
)

_DEFAULT_USER_VALUE: dict[str, dict[str, object]] = {
    "conversational-co-creation": {
        "headline": "채팅 Co-Creation",
        "user_value": "로그인·결제 후 채팅으로 템플릿·플랫폼 blueprint를 요청할 수 있습니다.",
        "suggested_prompt": "전자계약 funnel과 마이페이지가 있는 랜딩 템플릿 제안해줘",
        "proposable_to_user": True,
    },
    "reference-url-style": {
        "headline": "URL 참조 feel",
        "user_value": "원하는 사이트 URL을 주면 유사한 느낌의 구조로 제안합니다 (verbatim 복제 없음).",
        "suggested_prompt": "https://example.com/ 느낌으로 hero와 checkout 구성해줘",
        "proposable_to_user": True,
    },
    "co_creation_codegen": {
        "headline": "승인 후 variant 생성",
        "user_value": "operator 승인 blueprint에서 실행 가능한 variant stub이 생성됩니다.",
        "suggested_prompt": "승인된 blueprint로 codegen 진행",
        "proposable_to_user": False,
    },
    "co_creation_preview": {
        "headline": "Tenant Preview Sandbox",
        "user_value": "격리 preview URL에서 결과를 확인하고 feedback으로 수정할 수 있습니다.",
        "suggested_prompt": "preview에서 hero CTA를 더 강조해줘",
        "proposable_to_user": True,
    },
    "co_creation_deploy": {
        "headline": "단계적 배포",
        "user_value": "SHADOW→PILOT→PRODUCTION 단계 rollout (operator+eternian gate).",
        "suggested_prompt": "",
        "proposable_to_user": False,
    },
    "billing-entitlement": {
        "headline": "Billing 연동",
        "user_value": "유료 capability gate가 billing SoT API로 검증됩니다.",
        "suggested_prompt": "",
        "proposable_to_user": False,
    },
    "cross-platform-learning": {
        "headline": "Cross-platform 학습",
        "user_value": "더 풍부한 evidence로 사용자 요청에 맞는 제안 품질이 올라갑니다.",
        "suggested_prompt": "",
        "proposable_to_user": False,
    },
}


@dataclass(frozen=True)
class ImprovementProcessStep:
    step_index: int
    contributor: str
    improvement_ref: str
    improvement_summary: str
    capabilities_gained: tuple[str, ...]
    captured_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "step_index": self.step_index,
            "contributor": self.contributor,
            "improvement_ref": self.improvement_ref,
            "improvement_summary": self.improvement_summary,
            "capabilities_gained": list(self.capabilities_gained),
            "captured_at": self.captured_at.isoformat(),
        }


@dataclass(frozen=True)
class AddedFeatureInsight:
    feature_id: str
    headline: str
    intent_summary: str
    user_value: str
    process_phase: str
    proposable_to_user: bool
    suggested_prompt: str
    contributor_chain: tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "headline": self.headline,
            "intent_summary": self.intent_summary,
            "user_value": self.user_value,
            "process_phase": self.process_phase,
            "proposable_to_user": self.proposable_to_user,
            "suggested_prompt": self.suggested_prompt,
            "contributor_chain": list(self.contributor_chain),
        }


@dataclass(frozen=True)
class EvolutionImprovementAnalysis:
    comparison_digest: str
    baseline_snapshot_id: str
    candidate_snapshot_id: str
    process_narrative: str
    process_steps: tuple[ImprovementProcessStep, ...]
    added_features: tuple[AddedFeatureInsight, ...]
    pipeline_progression: tuple[str, ...]
    analysis_digest: str
    analyzed_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.self-evolution-improvement-analysis/v1",
            "comparison_digest": self.comparison_digest,
            "baseline_snapshot_id": self.baseline_snapshot_id,
            "candidate_snapshot_id": self.candidate_snapshot_id,
            "process_narrative": self.process_narrative,
            "process_steps": [item.to_document() for item in self.process_steps],
            "added_features": [item.to_document() for item in self.added_features],
            "pipeline_progression": list(self.pipeline_progression),
            "analysis_digest": self.analysis_digest,
            "analyzed_at": self.analyzed_at.isoformat(),
        }


_FEATURE_ALIASES: dict[str, str] = {
    "co_creation_chat": "conversational-co-creation",
    "co_creation_build": "co-creation-phase4-roadmap",
    "co_creation_codegen": "co-creation-phase4-roadmap",
    "co_creation_preview": "co-creation-phase4-roadmap",
    "co_creation_deploy": "co-creation-phase4-roadmap",
    "billing_entitlement": "billing-entitlement",
    "cross_platform_learning": "cross-platform-learning",
    "self_evolution_compare": "self-evolution-analysis",
}


def _normalize_feature_id(feature_id: str) -> str:
    return _FEATURE_ALIASES.get(feature_id, feature_id.replace("_", "-"))


def _load_feature_intent(foundry_root: Path, feature_id: str) -> dict[str, object] | None:
    normalized = _normalize_feature_id(feature_id)
    path = foundry_root / "knowledge" / "feature-intents" / f"{normalized}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _process_phase_for(feature_id: str) -> str:
    for marker, label in _PIPELINE_PROCESS_ORDER:
        if marker.replace("_", "-") in feature_id or marker in feature_id:
            return label
    return "capability expansion"


def _resolve_feature_insight(
    *,
    foundry_root: Path,
    feature_id: str,
    contributor_chain: tuple[str, ...],
) -> AddedFeatureInsight:
    intent = _load_feature_intent(foundry_root, feature_id)
    normalized = _normalize_feature_id(feature_id)
    defaults = _DEFAULT_USER_VALUE.get(normalized, {})
    if not defaults:
        defaults = _DEFAULT_USER_VALUE.get(feature_id, {})
    intent_summary = str((intent or {}).get("intent_summary", "")) or str(
        defaults.get("user_value", f"새 capability: {feature_id}")
    )
    return AddedFeatureInsight(
        feature_id=feature_id,
        headline=str(defaults.get("headline", feature_id.replace("-", " ").title())),
        intent_summary=intent_summary,
        user_value=str(defaults.get("user_value", intent_summary)),
        process_phase=_process_phase_for(feature_id),
        proposable_to_user=bool(defaults.get("proposable_to_user", False)),
        suggested_prompt=str(defaults.get("suggested_prompt", "")),
        contributor_chain=contributor_chain,
    )


class ArkaonSelfEvolutionAnalysisEngine:
    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.compare_engine = ArkaonSelfEvolutionCompareEngine(foundry_root=self.foundry_root)
        self.analysis_root = self.foundry_root / "state" / "self-evolution" / "analyses"
        self.analysis_root.mkdir(parents=True, exist_ok=True)

    def _snapshots_between(
        self,
        *,
        baseline: CapabilitySnapshot,
        candidate: CapabilitySnapshot,
    ) -> tuple[CapabilitySnapshot, ...]:
        snapshots = self.compare_engine.list_snapshots(limit=100)
        selected = [
            item
            for item in snapshots
            if baseline.captured_at <= item.captured_at <= candidate.captured_at
        ]
        selected.sort(key=lambda item: item.captured_at)
        if not selected:
            return (baseline, candidate)
        return tuple(selected)

    def _build_process_steps(
        self,
        snapshots: tuple[CapabilitySnapshot, ...],
    ) -> tuple[ImprovementProcessStep, ...]:
        steps: list[ImprovementProcessStep] = []
        prior_caps: frozenset[str] = frozenset()
        for index, snapshot in enumerate(snapshots, start=1):
            gained = tuple(sorted(set(snapshot.capabilities) - prior_caps))
            prior_caps = frozenset(snapshot.capabilities)
            if index == 1 and not gained:
                continue
            steps.append(
                ImprovementProcessStep(
                    step_index=len(steps) + 1,
                    contributor=snapshot.contributor.value,
                    improvement_ref=snapshot.improvement_ref,
                    improvement_summary=snapshot.improvement_summary,
                    capabilities_gained=gained,
                    captured_at=snapshot.captured_at,
                )
            )
        return tuple(steps)

    def _build_process_narrative(
        self,
        *,
        report: EvolutionComparisonReport,
        steps: tuple[ImprovementProcessStep, ...],
        pipeline_progression: tuple[str, ...],
    ) -> str:
        parts: list[str] = []
        if steps:
            contributors = " → ".join(
                dict.fromkeys(step.contributor for step in steps)
            )
            parts.append(f"개선 주체 흐름: {contributors}")
        for step in steps:
            if step.capabilities_gained:
                parts.append(
                    f"[{step.contributor}] {step.improvement_summary} "
                    f"(+{', '.join(step.capabilities_gained[:3])})"
                )
        if report.new_capabilities:
            parts.append(f"추가 capability {len(report.new_capabilities)}개 분석 완료")
        if pipeline_progression:
            parts.append(f"pipeline 진행: {' → '.join(pipeline_progression)}")
        return " | ".join(parts) if parts else report.improved_summary

    def analyze_comparison(
        self,
        *,
        report: EvolutionComparisonReport,
        now: datetime,
    ) -> EvolutionImprovementAnalysis:
        if now.tzinfo is None:
            raise SelfEvolutionAnalysisRejected("TIMESTAMP", "timezone-aware timestamp required")
        baseline = self.compare_engine._load_snapshot_by_id(report.baseline_snapshot_id)
        candidate = self.compare_engine._load_snapshot_by_id(report.candidate_snapshot_id)
        journey = self._snapshots_between(baseline=baseline, candidate=candidate)
        process_steps = self._build_process_steps(journey)

        contributor_chain = tuple(dict.fromkeys(step.contributor for step in process_steps))
        added_features = tuple(
            _resolve_feature_insight(
                foundry_root=self.foundry_root,
                feature_id=feature_id,
                contributor_chain=contributor_chain,
            )
            for feature_id in report.new_capabilities
        )

        baseline_stages = set(baseline.pipeline_stages)
        pipeline_progression = tuple(
            label
            for marker, label in _PIPELINE_PROCESS_ORDER
            if marker in set(candidate.pipeline_stages) - baseline_stages
        )
        process_narrative = self._build_process_narrative(
            report=report,
            steps=process_steps,
            pipeline_progression=pipeline_progression,
        )

        body = {
            "comparison_digest": report.comparison_digest,
            "process_narrative": process_narrative,
            "added_feature_ids": [item.feature_id for item in added_features],
        }
        analysis_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        analysis = EvolutionImprovementAnalysis(
            comparison_digest=report.comparison_digest,
            baseline_snapshot_id=report.baseline_snapshot_id,
            candidate_snapshot_id=report.candidate_snapshot_id,
            process_narrative=process_narrative,
            process_steps=process_steps,
            added_features=added_features,
            pipeline_progression=pipeline_progression,
            analysis_digest=analysis_digest,
            analyzed_at=now,
        )
        path = self.analysis_root / f"{analysis_digest[:16]}.json"
        path.write_text(
            json.dumps(analysis.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return analysis

    def analyze(
        self,
        *,
        baseline_snapshot_id: str,
        candidate_snapshot_id: str,
        now: datetime,
    ) -> EvolutionImprovementAnalysis:
        try:
            report = self.compare_engine.compare(
                baseline_snapshot_id=baseline_snapshot_id,
                candidate_snapshot_id=candidate_snapshot_id,
                now=now,
            )
        except SelfEvolutionRejected as error:
            raise SelfEvolutionAnalysisRejected(error.code, str(error)) from error
        return self.analyze_comparison(report=report, now=now)

    def analyze_latest(self, *, now: datetime) -> EvolutionImprovementAnalysis:
        try:
            report = self.compare_engine.compare_latest_pair(now=now)
        except SelfEvolutionRejected as error:
            raise SelfEvolutionAnalysisRejected(error.code, str(error)) from error
        return self.analyze_comparison(report=report, now=now)

    def load_analysis(self, analysis_digest: str) -> EvolutionImprovementAnalysis:
        path = self.analysis_root / f"{analysis_digest[:16]}.json"
        if not path.is_file():
            for candidate in self.analysis_root.glob("*.json"):
                document = json.loads(candidate.read_text(encoding="utf-8"))
                if document.get("analysis_digest") == analysis_digest:
                    path = candidate
                    break
            else:
                raise SelfEvolutionAnalysisRejected("ANALYSIS_NOT_FOUND", "analysis not found")
        document = json.loads(path.read_text(encoding="utf-8"))
        return EvolutionImprovementAnalysis(
            comparison_digest=str(document["comparison_digest"]),
            baseline_snapshot_id=str(document["baseline_snapshot_id"]),
            candidate_snapshot_id=str(document["candidate_snapshot_id"]),
            process_narrative=str(document["process_narrative"]),
            process_steps=tuple(
                ImprovementProcessStep(
                    step_index=int(item["step_index"]),
                    contributor=str(item["contributor"]),
                    improvement_ref=str(item["improvement_ref"]),
                    improvement_summary=str(item["improvement_summary"]),
                    capabilities_gained=tuple(item.get("capabilities_gained") or ()),
                    captured_at=datetime.fromisoformat(str(item["captured_at"])),
                )
                for item in document.get("process_steps") or []
            ),
            added_features=tuple(
                AddedFeatureInsight(
                    feature_id=str(item["feature_id"]),
                    headline=str(item["headline"]),
                    intent_summary=str(item["intent_summary"]),
                    user_value=str(item["user_value"]),
                    process_phase=str(item["process_phase"]),
                    proposable_to_user=bool(item.get("proposable_to_user")),
                    suggested_prompt=str(item.get("suggested_prompt", "")),
                    contributor_chain=tuple(item.get("contributor_chain") or ()),
                )
                for item in document.get("added_features") or []
            ),
            pipeline_progression=tuple(document.get("pipeline_progression") or ()),
            analysis_digest=str(document["analysis_digest"]),
            analyzed_at=datetime.fromisoformat(str(document["analyzed_at"])),
        )
