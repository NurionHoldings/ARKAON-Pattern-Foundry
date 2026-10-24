"""Assess fundamental learning improvement gates (strict evidence; no auto-apply)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from .fundamental_learning_evidence import (
    expected_schedule_hours,
    failure_feedback_chain_valid,
    held_out_task_valid,
    hourly_record_observed_at,
    improvement_metrics_valid,
    iter_hourly_learning_records,
    lesson_is_verified_for_linkage,
    load_reflective_lesson,
    verify_lesson_work_trace,
)
from .lesson_work_trace import LessonWorkTraceStore


class GateStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PARTIAL = "PARTIAL"
    CANDIDATE_EVIDENCE = "CANDIDATE_EVIDENCE"
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
    efficacy_validation: str
    stages: tuple[StageAssessment, ...]
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.fundamental-learning-gate-report/v2",
            "evaluated_at": self.evaluated_at.isoformat(),
            "overall_status": self.overall_status,
            "operational_apply_complete": self.operational_apply_complete,
            "efficacy_validation": self.efficacy_validation,
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
        digest = sha256(
            json.dumps(
                {
                    "evaluated_at": evaluated_at.isoformat(),
                    "stages": [s.status.value for s in assessments],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return FundamentalLearningGateReport(
            evaluated_at=evaluated_at,
            overall_status=str(policy.get("overall_status", "MEMORY_FOUNDATION_ONLY")),
            operational_apply_complete=bool(policy.get("operational_apply_complete", False)),
            efficacy_validation=str(policy.get("efficacy_validation", "NEEDS_HARDENING")),
            stages=assessments,
            report_digest=digest,
        )

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
        lookback = 24
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            lookback = int(cfg.get("lookback_hours", 24))
        window_start = evaluated_at - timedelta(hours=lookback)
        evidence: list[str] = []
        blockers: list[str] = []

        records = iter_hourly_learning_records(self.foundry_root)
        in_window: list[dict] = []
        failed_runs = 0
        observed_slots: set[tuple[str, int]] = set()
        for record in records:
            observed = hourly_record_observed_at(record)
            if observed is None or observed < window_start or observed > evaluated_at:
                continue
            in_window.append(record)
            topic = record.get("topic", {})
            if isinstance(topic, dict):
                tz = str(topic.get("timezone", "UTC"))
                try:
                    local = observed.astimezone(ZoneInfo(tz))
                except (ValueError, KeyError):
                    local = observed
                observed_slots.add((local.strftime("%Y-%m-%d"), int(topic.get("local_hour", local.hour))))
            cycle = record.get("cycle", {})
            if isinstance(cycle, dict) and int(cycle.get("failed", 0)) > 0:
                failed_runs += int(cycle["failed"])
                if not cycle.get("failure_reason"):
                    blockers.append("hourly cycle failed without failure_reason")

        schedule_path = self.foundry_root / "config" / "arkaon-hourly-learning-schedule.json"
        expected = expected_schedule_hours(schedule_path, window_start=window_start, window_end=evaluated_at)
        missing_slots = len(expected - observed_slots) if expected else 0

        evidence.append(f"jsonl records in window (observed_at): {len(in_window)}")
        evidence.append(f"distinct scheduled slots observed: {len(observed_slots)}")
        if expected:
            evidence.append(f"expected hourly slots in window: {len(expected)}; missing: {missing_slots}")
        evidence.append(f"failed cycle rows: {failed_runs}")

        if not in_window:
            blockers.append("no hourly-learning jsonl rows with observed_at in lookback window")
        if missing_slots and expected:
            blockers.append(f"missing {missing_slots} scheduled hour slot(s) in window")
        if failed_runs:
            blockers.append("unresolved failed hourly cycles in window")

        status = GateStatus.NOT_STARTED
        if in_window and not blockers:
            status = GateStatus.READY_FOR_REVIEW
        elif in_window:
            status = GateStatus.PARTIAL
        return StageAssessment("execution_24h", title, status, criterion, tuple(evidence), tuple(blockers))

    def _assess_lesson_work_linkage(self, cfg: object) -> StageAssessment:
        title = "교훈을 작업에 연결"
        criterion = "실제 작업이 사용한 교훈과 결과를 추적"
        min_valid = 1
        store_rel = "knowledge/lesson-work-traces.jsonl"
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            min_valid = max(1, int(cfg.get("min_valid_traced_links", 1)))
            store_rel = str(cfg.get("store_path", store_rel))

        store = LessonWorkTraceStore(self.foundry_root / store_rel)
        traces = store.list_traces()
        valid = 0
        digest_failures = 0
        lesson_missing = 0
        lesson_unverified = 0
        for trace in traces:
            ok, _reason = verify_lesson_work_trace(trace)
            if not ok:
                digest_failures += 1
                continue
            lesson_id = str(trace.get("lesson_id", ""))
            lesson = load_reflective_lesson(self.foundry_root, lesson_id)
            if lesson is None:
                lesson_missing += 1
                continue
            if not lesson_is_verified_for_linkage(lesson):
                lesson_unverified += 1
                continue
            lesson_digest = lesson.get("evidence_digest")
            if trace.get("lesson_evidence_digest") and trace["lesson_evidence_digest"] != lesson_digest:
                digest_failures += 1
                continue
            valid += 1

        evidence = (
            f"traces total={len(traces)} valid={valid} (min {min_valid})",
            f"digest_invalid={digest_failures} lesson_missing={lesson_missing} lesson_unverified={lesson_unverified}",
        )
        blockers: list[str] = []
        if valid < min_valid:
            blockers.append("insufficient verified lesson-work links")
        if digest_failures:
            blockers.append("trace digest or outcome digest mismatch")
        if lesson_missing or lesson_unverified:
            blockers.append("lesson missing or not ACCEPT with evidence_digest")

        status = GateStatus.NOT_STARTED
        if valid >= min_valid:
            status = GateStatus.READY_FOR_REVIEW
        elif traces:
            status = GateStatus.PARTIAL
        return StageAssessment("lesson_work_linkage", title, status, criterion, evidence, tuple(blockers))

    def _assess_held_out_comparison(self, cfg: object) -> StageAssessment:
        title = "학습 효과 비교"
        criterion = "학습자료와 분리한 과제 20개 이상 전후 비교"
        min_tasks = 20
        registry = "state/held-out-evaluation/tasks.json"
        training_fp_path = "config/training-corpus-fingerprint.txt"
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            min_tasks = max(1, int(cfg.get("min_held_out_tasks", 20)))
            registry = str(cfg.get("registry_path", registry))
            training_fp_path = str(cfg.get("training_corpus_fingerprint_path", training_fp_path))

        training_fp = None
        fp_file = self.foundry_root / training_fp_path
        if fp_file.is_file():
            training_fp = fp_file.read_text(encoding="utf-8").strip() or None

        path = self.foundry_root / registry
        blockers: list[str] = []
        evidence: list[str] = []
        valid_tasks = 0
        seen_ids: set[str] = set()
        if path.is_file():
            document = json.loads(path.read_text(encoding="utf-8"))
            tasks = document.get("tasks", [])
            if not isinstance(tasks, list):
                blockers.append("held-out registry tasks must be a list")
            else:
                for item in tasks:
                    if not isinstance(item, dict):
                        continue
                    task_id = str(item.get("task_id", ""))
                    if task_id in seen_ids:
                        blockers.append(f"duplicate task_id {task_id}")
                        continue
                    if task_id:
                        seen_ids.add(task_id)
                    ok, reason = held_out_task_valid(item, training_fingerprint=training_fp)
                    if ok:
                        valid_tasks += 1
                    else:
                        blockers.append(f"task {task_id or '?'}: {reason}")
                evidence.append(f"held-out tasks valid={valid_tasks}/{len(tasks)}")
        else:
            blockers.append(f"{registry} not created")
        if valid_tasks < min_tasks:
            blockers.append(f"need at least {min_tasks} fully evidenced held-out tasks")

        status = GateStatus.NOT_STARTED
        if valid_tasks >= min_tasks and not any("duplicate" in b for b in blockers):
            status = GateStatus.READY_FOR_REVIEW
        elif valid_tasks or path.is_file():
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
        blockers = ["human_signoff_required; automated assessor never grants improvement recognition"]
        status = GateStatus.NOT_STARTED
        if path.is_file():
            document = json.loads(path.read_text(encoding="utf-8"))
            ok, metric_blockers = improvement_metrics_valid(document)
            evidence.append(f"metrics.json strict validation: {ok}")
            if not ok:
                blockers.extend(metric_blockers)
                status = GateStatus.PARTIAL
            else:
                status = GateStatus.READY_FOR_REVIEW
        else:
            evidence.append("metrics.json not recorded")
            blockers.append("metrics.json missing")
        return StageAssessment("improvement_recognition", title, status, criterion, tuple(evidence), tuple(blockers))

    def _assess_failure_feedback(self, cfg: object) -> StageAssessment:
        title = "실패 환류"
        criterion = "실패 원인을 다음 학습과제로 만들고 독립 검토"
        inbox_dirs = ("inbox/eternian-review", "inbox/research", "inbox/operator-decision")
        if isinstance(cfg, dict):
            title = str(cfg.get("title", title))
            criterion = str(cfg.get("completion_criterion", criterion))
            raw = cfg.get("inbox_paths")
            if isinstance(raw, list) and raw:
                inbox_dirs = tuple(str(item) for item in raw)

        chain_valid = 0
        keyword_candidates = 0
        evidence: list[str] = []
        blockers: list[str] = []

        for rel in inbox_dirs:
            directory = self.foundry_root / rel
            if not directory.is_dir():
                continue
            for path in directory.glob("*.json"):
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                ok, _ = failure_feedback_chain_valid(document)
                if ok:
                    chain_valid += 1
                    continue
                schema = str(document.get("schema_version", ""))
                summary = str(document.get("summary", "")).lower()
                if (
                    "learning" in schema
                    or "impediment" in schema
                    or "lesson" in schema
                    or "failure" in summary
                    or "learning" in summary
                ):
                    keyword_candidates += 1

        evidence.append(f"complete failure→learning→review chains: {chain_valid}")
        evidence.append(f"keyword-only candidate packets: {keyword_candidates}")

        if chain_valid >= 1:
            status = GateStatus.READY_FOR_REVIEW
        elif keyword_candidates >= 1:
            status = GateStatus.CANDIDATE_EVIDENCE
            blockers.append(
                "candidate packets only; not evidence of failure reflux (need failure_source_ref, "
                "root_cause_code, derived_learning_task_id, independent_review_ref)"
            )
        else:
            status = GateStatus.NOT_STARTED
            blockers.append("no failure feedback chain or candidate packets")
        return StageAssessment("failure_feedback_loop", title, status, criterion, tuple(evidence), tuple(blockers))
