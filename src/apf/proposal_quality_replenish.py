"""Replenish learning assets via supplemental analysis, then enable better re-proposal."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .proposal_quality_score import (
    ProposalQualityRejected,
    ProposalQualityReport,
    ProposalQualityScorer,
    assert_proposal_quality_gate,
)

_DISSATISFACTION = re.compile(
    r"(맘에\s*안|불만|다시\s*제안|부족|아쉬|품질|별로|마음에\s*들지|unsatisfied|not\s+good|redo|try\s+again)",
    re.IGNORECASE,
)

_TOKEN_FROM_MESSAGE: tuple[tuple[str, str], ...] = (
    (r"전자계약|e-contract|esign", "landing-pattern:e-contract-flow"),
    (r"hero|히어로|cta", "landing-pattern:hero-single-cta"),
    (r"마이페이지|dashboard|대시보드", "landing-pattern:mypage-dashboard"),
    (r"4단계|four-step|process", "landing-pattern:four-step-process"),
    (r"비교|comparison", "landing-pattern:comparison-table"),
)


class ProposalQualityReplenishRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProposalQualityReplenishPolicy:
    enabled: bool = True
    max_replenish_attempts_per_request: int = 1
    max_actions_per_replenish: int = 2
    replenish_on_gate_fail: bool = True
    replenish_on_user_dissatisfaction: bool = True
    minimum_artifacts: int = 1
    """Replenish on user dissatisfaction only when score is below this ceiling."""
    replenish_user_dissatisfaction_score_ceiling: float = 0.55

    @classmethod
    def load(cls, path: Path) -> ProposalQualityReplenishPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.proposal-quality/v1":
            raise ProposalQualityReplenishRejected("POLICY_SCHEMA", "unsupported proposal quality schema")
        return cls(
            enabled=bool(document.get("replenish_enabled", document.get("enabled", True))),
            max_replenish_attempts_per_request=max(
                1, int(document.get("max_replenish_attempts_per_request", 1))
            ),
            max_actions_per_replenish=max(1, int(document.get("max_actions_per_replenish", 2))),
            replenish_on_gate_fail=bool(document.get("replenish_on_gate_fail", True)),
            replenish_on_user_dissatisfaction=bool(document.get("replenish_on_user_dissatisfaction", True)),
            minimum_artifacts=max(1, int(document.get("minimum_experience_artifacts", 1))),
            replenish_user_dissatisfaction_score_ceiling=float(
                document.get("replenish_user_dissatisfaction_score_ceiling", 0.55)
            ),
        )


@dataclass(frozen=True)
class ReplenishAction:
    action_type: str
    target_path: str
    summary: str

    def to_document(self) -> dict[str, object]:
        return {
            "action_type": self.action_type,
            "target_path": self.target_path,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ProposalQualityReplenishReport:
    platform_id: str
    trigger: str
    before_score: float
    after_score: float
    gate_pass_after: bool
    actions: tuple[ReplenishAction, ...]
    replenish_digest: str
    replenished_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.proposal-quality-replenish/v1",
            "platform_id": self.platform_id,
            "trigger": self.trigger,
            "before_score": round(self.before_score, 4),
            "after_score": round(self.after_score, 4),
            "gate_pass_after": self.gate_pass_after,
            "actions": [item.to_document() for item in self.actions],
            "replenish_digest": self.replenish_digest,
            "replenished_at": self.replenished_at.isoformat(),
        }


def user_dissatisfaction_detected(message: str) -> bool:
    return bool(_DISSATISFACTION.search(message))


def assets_insufficient_for_better_proposal(
    report: ProposalQualityReport,
    *,
    minimum_score: float,
    score_ceiling: float,
) -> bool:
    """True when learning assets are too thin to support a high-quality re-proposal."""
    if not report.gate_pass:
        return True
    breakdown = report.breakdown
    if breakdown.landing_patterns == 0 or breakdown.cross_platform_learning == 0:
        return True
    if report.score < minimum_score:
        return True
    return report.score < score_ceiling


def _tokens_from_message(message: str) -> frozenset[str]:
    tokens: set[str] = set()
    for pattern, token in _TOKEN_FROM_MESSAGE:
        if re.search(pattern, message, re.IGNORECASE):
            tokens.add(token)
    return frozenset(tokens)


class ProposalQualityReplenishEngine:
    def __init__(self, *, foundry_root: Path, policy: ProposalQualityReplenishPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-proposal-quality.json"
        self.policy = policy or ProposalQualityReplenishPolicy.load(config)
        self.scorer = ProposalQualityScorer(foundry_root=self.foundry_root)
        self.store_root = self.foundry_root / "state" / "proposal-quality" / "replenish"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def list_recent(self, *, limit: int = 20) -> tuple[ProposalQualityReplenishReport, ...]:
        if not self.store_root.is_dir():
            return ()
        paths = sorted(self.store_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        reports: list[ProposalQualityReplenishReport] = []
        for path in paths[:limit]:
            document = json.loads(path.read_text(encoding="utf-8"))
            actions = tuple(
                ReplenishAction(
                    action_type=str(item["action_type"]),
                    target_path=str(item["target_path"]),
                    summary=str(item["summary"]),
                )
                for item in document.get("actions") or ()
            )
            reports.append(
                ProposalQualityReplenishReport(
                    platform_id=str(document["platform_id"]),
                    trigger=str(document["trigger"]),
                    before_score=float(document["before_score"]),
                    after_score=float(document["after_score"]),
                    gate_pass_after=bool(document["gate_pass_after"]),
                    actions=actions,
                    replenish_digest=str(document["replenish_digest"]),
                    replenished_at=datetime.fromisoformat(str(document["replenished_at"])),
                )
            )
        return tuple(reports)

    def _decide_replenish(
        self,
        before: ProposalQualityReport,
        *,
        user_dissatisfied: bool,
    ) -> tuple[str, bool]:
        if not self.policy.enabled:
            return "", False
        if not before.gate_pass and self.policy.replenish_on_gate_fail:
            return "GATE_FAIL", True
        if user_dissatisfied and self.policy.replenish_on_user_dissatisfaction:
            minimum = self.scorer.policy.minimum_proposal_quality_score
            if assets_insufficient_for_better_proposal(
                before,
                minimum_score=minimum,
                score_ceiling=self.policy.replenish_user_dissatisfaction_score_ceiling,
            ):
                return "USER_DISSATISFACTION", True
        return "", False

    def _gap_priorities(self, report: ProposalQualityReport) -> tuple[str, ...]:
        breakdown = report.breakdown
        policy = self.scorer.policy
        ratios = [
            (
                breakdown.landing_patterns / policy.full_score_landing_patterns,
                "landing_patterns",
            ),
            (
                breakdown.cross_platform_learning / policy.full_score_cross_platform_learning,
                "cross_platform_learning",
            ),
            (
                breakdown.reflective_lessons / policy.full_score_reflective_lessons,
                "reflective_lessons",
            ),
            (
                breakdown.self_evolution_analyses / policy.full_score_self_evolution_analyses,
                "self_evolution_analyses",
            ),
        ]
        ratios.sort(key=lambda item: item[0])
        return tuple(name for _ratio, name in ratios)

    def _add_landing_pattern(
        self,
        *,
        platform_id: str,
        message: str,
        now: datetime,
    ) -> ReplenishAction:
        tokens = _tokens_from_message(message)
        token = min(tokens) if tokens else "landing-pattern:hero-single-cta"
        pattern_id = f"landing.replenish.{platform_id.lower()}.{token.split(':')[-1]}"
        digest = sha256(f"{platform_id}|{message}|{token}|{now.isoformat()}".encode()).hexdigest()
        path = (
            self.foundry_root
            / "knowledge"
            / "landing-structure-patterns"
            / "proposed"
            / f"{pattern_id}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": "apf.landing-structure-pattern-proposal/v1",
            "pattern_id": pattern_id,
            "pattern_token": token,
            "platform_ids": [platform_id],
            "summary": f"Replenish analysis: {token} evidence seeded for {platform_id} from user intent.",
            "evidence_digests": [digest],
            "review_status": "PROPOSED",
            "automatic_promotion_allowed": False,
            "production_change_allowed": False,
            "replenish_source": "proposal-quality-replenish",
        }
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return ReplenishAction(
            action_type="LANDING_PATTERN",
            target_path=path.relative_to(self.foundry_root).as_posix(),
            summary=f"added pattern {pattern_id} for {token}",
        )

    def _add_cross_platform_learning(
        self,
        *,
        platform_id: str,
        message: str,
        now: datetime,
    ) -> ReplenishAction:
        digest = sha256(f"{platform_id}|{message}|{now.isoformat()}".encode()).hexdigest()
        stamp = now.strftime("%Y-%m-%d")
        path = self.foundry_root / "state" / "cross-platform-learning" / f"{stamp}-{digest[:12]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": "apf.cross-platform-learning-supplement/v1",
            "evaluated_at": now.isoformat(),
            "platform_id": platform_id,
            "trigger": "proposal-quality-replenish",
            "intent_summary": message.strip()[:240],
            "lesson_seeds": [
                {
                    "platform_scope": platform_id,
                    "pattern_id": f"replenish.{digest[:12]}",
                    "evidence_digest": digest,
                    "summary": "Supplemental cross-platform analysis for better proposal.",
                }
            ],
            "production_change_allowed": False,
        }
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return ReplenishAction(
            action_type="CROSS_PLATFORM_LEARNING",
            target_path=path.relative_to(self.foundry_root).as_posix(),
            summary="supplemental cross-platform learning record",
        )

    def _add_reflective_lesson(
        self,
        *,
        platform_id: str,
        message: str,
        now: datetime,
    ) -> ReplenishAction:
        lesson_id = sha256(f"lesson|{platform_id}|{message}|{now.isoformat()}".encode()).hexdigest()[:16]
        path = self.foundry_root / "knowledge" / "reflective-lessons" / f"replenish-{lesson_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256(message.encode()).hexdigest()
        document = {
            "schema_version": "apf.reflective-lesson/v1",
            "lesson_id": f"replenish-{lesson_id}",
            "case_id": f"replenish-{platform_id}",
            "platform_scope": platform_id,
            "outcome": "DEFER",
            "principle": "Proposal quality gap triggered supplemental analysis before re-proposal.",
            "reusable_pattern": "replenish-then-repropose",
            "failure_or_rejection_reason": message.strip()[:240],
            "evidence_digest": digest,
            "recorded_at": now.isoformat(),
            "contains_operational_data": False,
        }
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return ReplenishAction(
            action_type="REFLECTIVE_LESSON",
            target_path=path.relative_to(self.foundry_root).as_posix(),
            summary="reflective lesson seed from replenish analysis",
        )

    def _add_self_evolution_analysis(self, *, platform_id: str, now: datetime) -> ReplenishAction:
        from .arkaon_self_evolution_analysis import (
            ArkaonSelfEvolutionAnalysisEngine,
            SelfEvolutionAnalysisRejected,
        )
        from .arkaon_self_evolution_compare import (
            ArkaonSelfEvolutionCompareEngine,
            ImprovementContributor,
        )

        compare = ArkaonSelfEvolutionCompareEngine(foundry_root=self.foundry_root)
        compare.capture_snapshot(
            contributor=ImprovementContributor.SYSTEM,
            improvement_ref=f"replenish-{platform_id}",
            improvement_summary="proposal quality replenish — supplemental analysis complete",
            now=now,
        )
        analysis_engine = ArkaonSelfEvolutionAnalysisEngine(foundry_root=self.foundry_root)
        try:
            analysis = analysis_engine.analyze_latest(now=now)
            target = f"state/self-evolution/analyses/{analysis.analysis_digest[:16]}.json"
        except SelfEvolutionAnalysisRejected:
            target = "state/self-evolution/analyses/"
        return ReplenishAction(
            action_type="SELF_EVOLUTION_ANALYSIS",
            target_path=target,
            summary="evolution analysis after replenish",
        )

    def _execute_action(self, gap: str, *, platform_id: str, message: str, now: datetime) -> ReplenishAction:
        if gap == "landing_patterns":
            return self._add_landing_pattern(platform_id=platform_id, message=message, now=now)
        if gap == "cross_platform_learning":
            return self._add_cross_platform_learning(platform_id=platform_id, message=message, now=now)
        if gap == "reflective_lessons":
            return self._add_reflective_lesson(platform_id=platform_id, message=message, now=now)
        return self._add_self_evolution_analysis(platform_id=platform_id, now=now)

    def replenish(
        self,
        *,
        platform_id: str,
        message: str,
        trigger: str,
        now: datetime,
    ) -> ProposalQualityReplenishReport:
        if now.tzinfo is None:
            raise ProposalQualityReplenishRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise ProposalQualityReplenishRejected("DISABLED", "proposal quality replenish is disabled")

        before = self.scorer.evaluate(now=now)
        gaps = self._gap_priorities(before)
        actions: list[ReplenishAction] = []
        for gap in gaps[: self.policy.max_actions_per_replenish]:
            actions.append(self._execute_action(gap, platform_id=platform_id, message=message, now=now))

        after = self.scorer.evaluate(now=now)
        body = {
            "platform_id": platform_id,
            "trigger": trigger,
            "before_score": before.score,
            "after_score": after.score,
            "actions": [item.to_document() for item in actions],
        }
        replenish_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        report = ProposalQualityReplenishReport(
            platform_id=platform_id,
            trigger=trigger,
            before_score=before.score,
            after_score=after.score,
            gate_pass_after=after.gate_pass,
            actions=tuple(actions),
            replenish_digest=replenish_digest,
            replenished_at=now,
        )
        path = self.store_root / f"{replenish_digest[:16]}.json"
        path.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self.scorer.evaluate_and_persist(now=now)
        return report

    def try_replenish_for_gate(
        self,
        *,
        platform_id: str,
        message: str,
        user_dissatisfied: bool,
        minimum_artifacts: int,
        now: datetime,
    ) -> tuple[ProposalQualityReport | None, ProposalQualityReplenishReport | None]:
        before = self.scorer.evaluate(now=now)
        trigger, needs_replenish = self._decide_replenish(before, user_dissatisfied=user_dissatisfied)
        if not needs_replenish:
            return None, None

        replenish_report = self.replenish(
            platform_id=platform_id,
            message=message,
            trigger=trigger,
            now=now,
        )
        try:
            quality = assert_proposal_quality_gate(
                foundry_root=self.foundry_root,
                minimum_artifacts=minimum_artifacts,
            )
        except ProposalQualityRejected:
            return None, replenish_report
        return quality, replenish_report


def resolve_proposal_quality_with_replenish(
    *,
    foundry_root: Path,
    platform_id: str,
    message: str,
    minimum_artifacts: int,
    now: datetime,
) -> tuple[ProposalQualityReport, ProposalQualityReplenishReport | None]:
    """Gate check with optional replenish → re-evaluate before proposal generation."""
    engine = ProposalQualityReplenishEngine(foundry_root=foundry_root)
    user_dissatisfied = user_dissatisfaction_detected(message)
    initial_error: ProposalQualityRejected | None = None
    quality: ProposalQualityReport | None = None

    try:
        quality = assert_proposal_quality_gate(
            foundry_root=foundry_root,
            minimum_artifacts=minimum_artifacts,
        )
    except ProposalQualityRejected as error:
        if error.code == "INSUFFICIENT_EXPERIENCE":
            raise
        initial_error = error

    before = quality or engine.scorer.evaluate(now=now)
    trigger, should_replenish = engine._decide_replenish(before, user_dissatisfied=user_dissatisfied)
    replenish_report: ProposalQualityReplenishReport | None = None

    if should_replenish:
        replenish_report = engine.replenish(
            platform_id=platform_id,
            message=message,
            trigger=trigger,
            now=now,
        )
        try:
            quality = assert_proposal_quality_gate(
                foundry_root=foundry_root,
                minimum_artifacts=minimum_artifacts,
            )
        except ProposalQualityRejected as error:
            if initial_error is not None:
                raise initial_error from error
            raise

    if quality is None and initial_error is not None:
        raise initial_error
    assert quality is not None
    return quality, replenish_report


def try_replenish_and_pass_gate(
    *,
    foundry_root: Path,
    platform_id: str,
    message: str,
    minimum_artifacts: int,
    user_dissatisfied: bool,
    now: datetime,
) -> tuple[ProposalQualityReport | None, ProposalQualityReplenishReport | None]:
    engine = ProposalQualityReplenishEngine(foundry_root=foundry_root)
    return engine.try_replenish_for_gate(
        platform_id=platform_id,
        message=message,
        user_dissatisfied=user_dissatisfied,
        minimum_artifacts=minimum_artifacts,
        now=now,
    )
