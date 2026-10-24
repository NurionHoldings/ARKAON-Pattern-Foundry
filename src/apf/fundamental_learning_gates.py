"""Assess fundamental learning improvement gates (read-only; no auto-apply)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from .lesson_work_trace import LessonWorkTraceStore


class GateStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PARTIAL = "PARTIAL"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


@dataclass(frozen=True)
class StageAssessment:
    stage_id: str
    title: str
    status: GateStatus
    completion_criterion: str
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class FundamentalLearningGateReport:
    evaluated_at: datetime
    overall_status: str
    operational_apply_complete: bool
    stages: tuple[StageAssessment, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.fundamental-learning-gate-report/v1",
            "evaluated_at": self.evaluated_at.isoformat(),
            "overall_status": self.overall_status,
            "operational_apply_complete": self.operational_apply_complete,
            "report_digest": self.report_digest,
            "stages": [
                {
                    "stage_id": stage.stage_id,
                    "title": stage.title,
                    "status": stage.status.value,
                    "completion_criterion": stage.completion_criterion,
                    "evidence": list(stage.evidence),
                    "blockers": list(stage.blockers),
                }
                for stage in self.stages
            ],
        }


class FundamentalLearningGateAssessor:
    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy_path = self.foundry_root / "config" / "arkaon-fundamental-learning-gates.json"
        self.store_root = self.foundry_root / "state" / "fundamental-learning-gates"

    def load_policy(self) -> dict[str, object]:
        if not self.policy_path.is_file():
            raise FileNotFoundError("config/arkaon-fundamental-learning-gates.json is missing")
        document = json.loads(self.policy_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.fundamental-learning-gates/v1":
            raise ValueError("unsupported fundamental learning gates schema")
        return document

    def assess(self, *, now: datetime | None = None) -> FundamentalLearningGateReport:
        evaluated_at = now or datetime.now(tz=UTC)
        if evaluated_at.tzinfo is None:
            raise ValueError("timezone-aware timestamp required")
        policy = self.load_policy()
        stages_cfg = policy.get("stages", {})
        if not isinstance(stages_cfg, dict):
            raise TypeError("stages must be an object")
        assessments = (
            self._assess_execution_24h(stages_cfg.get("execution_24h", {}), evaluated_at),
            self._assess_lesson_work_linkage(stages_cfg.get("lesson_work_linkage", {})),
            self._assess_held_out_comparison(stages_cfg.get("held_out_comparison", {})),
            self._assess_improvement_recognition(stages_cfg.get("improvement_recognition", {})),
            self._assess_failure_feedback(stages_cfg.get("failure_feedback_loop", {})),
        )
        document = {
            "evaluated_at": evaluated_at.isoformat(),
            "overall_status": policy.get("overall_status", "MEMORY_FOUNDATION_ONLY"),
            "operational_apply_complete": bool(policy.get("operational_apply_complete", False)),
            "stages": [stage.__dict__ for stage in assessments],
        }
        digest = sha256(json.dumps(document, sort_keys=True, default=str).encode()).hexdigest()
        report = FundamentalLearningGateReport(
            evaluated_at=evaluated_at,
            overall_status=str(policy.get("overall_status", "MEMORY_FOUNDATION_ONLY")),
            operational_apply_complete=bool(policy.get("operational_apply_complete", False)),
            stages=assessments,
            report_digest=digest,
        )
        return report

    def assess_and_persist(self, *, now: datetime | None = None, dry_run: bool = False) -> FundamentalLearningGateReport:
        report = self.assess(now=now)
        if not dry_run:
            self.store_root.mkdir(parents=True, exist_ok=True)
            target = self.store_root / f"{report.evaluated_at.strftime('%Y-%m-%d')}-{report.report_digest[:16]}.json"
            target.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return report

    def _assess_execution_24h(self, cfg: object, evaluated_at: datetime) -> StageAssessment:
        title = "실제 학습 실행 확인"
        criterion = "24시간 실행 기록에서 누락·오류 원인 확인"
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            lookback = int(cfg.get("lookback_hours", 24))
        else:
            lookback = 24
        cutoff = evaluated_at - timedelta(hours=lookback)
        evidence: list[str] = []
        blockers: list[str] = []
        hourly_dir = self.foundry_root / "state" / "hourly-learning"
        recent = []
        if hourly_dir.is_dir():
            for path in hourly_dir.glob("*.json"):
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                if mtime >= cutoff:
                    recent.append(path.name)
        evidence.append(f"hourly-learning files in window: {len(recent)}")
        current = self.foundry_root / "state" / "hourly-learning-current.json"
        if current.is_file():
            document = json.loads(current.read_text(encoding="utf-8"))
            cycle = document.get("cycle", {})
            if isinstance(cycle, dict):
                failed = int(cycle.get("failed", 0))
                if failed:
                    blockers.append(f"hourly-learning-current failed cycles: {failed}")
                evidence.append(f"hourly cycle collected={cycle.get('collected')} failed={failed}")
        else:
            blockers.append("state/hourly-learning-current.json missing")
        if not recent:
            blockers.append("no hourly-learning artifacts in lookback window")
        status = GateStatus.NOT_STARTED
        if recent and not blockers:
            status = GateStatus.READY_FOR_REVIEW
        elif recent or current.is_file():
            status = GateStatus.PARTIAL
        return StageAssessment("execution_24h", title, status, criterion, tuple(evidence), tuple(blockers))

    def _assess_lesson_work_linkage(self, cfg: object) -> StageAssessment:
        title = "교훈을 작업에 연결"
        criterion = "실제 작업이 사용한 교훈과 결과를 추적"
        min_links = 1
        store_rel = "knowledge/lesson-work-traces.jsonl"
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            min_links = max(1, int(cfg.get("min_traced_links", 1)))
            store_rel = str(cfg.get("store_path", store_rel))
        store = LessonWorkTraceStore(self.foundry_root / store_rel)
        traces = store.list_traces()
        lessons_dir = self.foundry_root / "knowledge" / "reflective-lessons"
        lesson_count = len(list(lessons_dir.glob("*.json"))) if lessons_dir.is_dir() else 0
        evidence = (
            f"reflective lessons on disk: {lesson_count}",
            f"lesson-work traces: {len(traces)} (min {min_links})",
        )
        blockers: list[str] = []
        if len(traces) < min_links:
            blockers.append("lesson-work trace store empty or below minimum")
        status = GateStatus.NOT_STARTED
        if len(traces) >= min_links:
            status = GateStatus.READY_FOR_REVIEW
        elif lesson_count or traces:
            status = GateStatus.PARTIAL
        return StageAssessment("lesson_work_linkage", title, status, criterion, evidence, tuple(blockers))

    def _assess_held_out_comparison(self, cfg: object) -> StageAssessment:
        title = "학습 효과 비교"
        criterion = "학습자료와 분리한 과제 20개 이상 전후 비교"
        min_tasks = 20
        registry = "state/held-out-evaluation/tasks.json"
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            min_tasks = max(1, int(cfg.get("min_held_out_tasks", 20)))
            registry = str(cfg.get("registry_path", registry))
        path = self.foundry_root / registry
        blockers: list[str] = []
        evidence: list[str] = []
        completed = 0
        if path.is_file():
            document = json.loads(path.read_text(encoding="utf-8"))
            tasks = document.get("tasks", [])
            if isinstance(tasks, list):
                for item in tasks:
                    if not isinstance(item, dict):
                        continue
                    if item.get("baseline_recorded") and item.get("post_learning_recorded"):
                        completed += 1
                evidence.append(f"held-out tasks with before/after: {completed}/{len(tasks)}")
            else:
                blockers.append("held-out registry tasks must be a list")
        else:
            blockers.append(f"{registry} not created")
            evidence.append("held-out evaluation registry missing")
        comparisons = self.foundry_root / "state" / "self-evolution" / "comparisons"
        comp_count = len(list(comparisons.glob("*.json"))) if comparisons.is_dir() else 0
        evidence.append(f"self-evolution comparisons: {comp_count}")
        if completed < min_tasks:
            blockers.append(f"need at least {min_tasks} held-out before/after tasks")
        status = GateStatus.NOT_STARTED
        if completed >= min_tasks:
            status = GateStatus.READY_FOR_REVIEW
        elif completed or comp_count:
            status = GateStatus.PARTIAL
        return StageAssessment("held_out_comparison", title, status, criterion, tuple(evidence), tuple(blockers))

    def _assess_improvement_recognition(self, cfg: object) -> StageAssessment:
        title = "개선 인정"
        criterion = "안전 실패·기존 기능 회귀 없이 목표 실패 감소"
        metrics_path = "state/held-out-evaluation/metrics.json"
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            metrics_path = str(cfg.get("metrics_path", metrics_path))
        path = self.foundry_root / metrics_path
        evidence: list[str] = []
        blockers = [
            "requires signed human review; automated gate does not self-certify",
            "record CI green + held-out failure delta in metrics.json",
        ]
        if path.is_file():
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("regression_free") and document.get("target_failure_delta") is not None:
                evidence.append("metrics.json present with regression_free and target_failure_delta")
                blockers = [b for b in blockers if "record CI" not in b]
            else:
                evidence.append("metrics.json present but incomplete")
        else:
            evidence.append("metrics.json not recorded")
        status = GateStatus.NOT_STARTED if path.is_file() is False else GateStatus.PARTIAL
        return StageAssessment("improvement_recognition", title, status, criterion, tuple(evidence), tuple(blockers))

    def _assess_failure_feedback(self, cfg: object) -> StageAssessment:
        title = "실패 환류"
        criterion = "실패 원인을 다음 학습과제로 만들고 독립 검토"
        min_packets = 1
        inbox_dirs = ("inbox/eternian-review", "inbox/research")
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            min_packets = max(1, int(cfg.get("min_failure_derived_packets", 1)))
            raw = cfg.get("inbox_paths")
            if isinstance(raw, list) and raw:
                inbox_dirs = tuple(str(item) for item in raw)
        derived = 0
        evidence: list[str] = []
        for rel in inbox_dirs:
            directory = self.foundry_root / rel
            if not directory.is_dir():
                continue
            for path in directory.glob("*.json"):
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                schema = str(document.get("schema_version", ""))
                summary = str(document.get("summary", "")).lower()
                if "learning" in schema or "lesson" in schema or "failure" in summary or "impediment" in schema:
                    derived += 1
        evidence.append(f"failure/learning derived inbox packets (heuristic): {derived}")
        blockers: list[str] = []
        if derived < min_packets:
            blockers.append("insufficient failure-derived learning packets for independent review")
        status = GateStatus.PARTIAL if derived else GateStatus.NOT_STARTED
        if derived >= min_packets:
            status = GateStatus.READY_FOR_REVIEW
        return StageAssessment("failure_feedback_loop", title, status, criterion, tuple(evidence), tuple(blockers))
