import json
from datetime import UTC, datetime
from pathlib import Path

from apf.fundamental_learning_gates import FundamentalLearningGateAssessor, GateStatus
from apf.lesson_work_trace import LessonWorkTraceStore


def test_lesson_work_trace_append_and_list(tmp_path: Path):
    store = LessonWorkTraceStore(tmp_path / "knowledge" / "lesson-work-traces.jsonl")
    store.append(lesson_id="lesson-1", work_ref="pr-105-ci", outcome="postgres-integration pass")
    rows = store.list_traces()
    assert len(rows) == 1
    assert rows[0]["lesson_id"] == "lesson-1"


def test_gate_assessor_memory_foundation_defaults(tmp_path: Path):
    policy = tmp_path / "config" / "arkaon-fundamental-learning-gates.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(
        json.dumps(
            {
                "schema_version": "apf.fundamental-learning-gates/v1",
                "overall_status": "MEMORY_FOUNDATION_ONLY",
                "operational_apply_complete": False,
                "stages": {},
            }
        ),
        encoding="utf-8",
    )
    hourly = tmp_path / "state" / "hourly-learning"
    hourly.mkdir(parents=True)
    (hourly / "cycle.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state" / "hourly-learning-current.json").write_text(
        json.dumps({"cycle": {"failed": 0, "collected": 1}}),
        encoding="utf-8",
    )
    assessor = FundamentalLearningGateAssessor(foundry_root=tmp_path)
    jsonl = tmp_path / "state" / "hourly-learning" / "2031-06-01.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=UTC)
    line = {
        "schema_version": "apf.hourly-learning-cycle/v1",
        "topic": {
            "local_hour": now.hour,
            "observed_at": now.isoformat(),
            "timezone": "UTC",
            "domain_id": "TEST",
            "topic_title": "test",
            "collect_all_domains": False,
        },
        "cycle": {"collected": 1, "failed": 0, "considered": 1, "denied": 0, "duplicate": 0, "skipped_out_of_topic": 0},
    }
    jsonl.write_text(json.dumps(line) + "\n", encoding="utf-8")
    schedule = tmp_path / "config" / "arkaon-hourly-learning-schedule.json"
    schedule.write_text(
        json.dumps({"schema_version": "apf.hourly-learning-schedule/v1", "enabled": True, "timezone": "UTC", "hours": []}),
        encoding="utf-8",
    )
    report = assessor.assess(now=now)
    by_id = {stage.stage_id: stage for stage in report.stages}
    assert report.overall_status == "MEMORY_FOUNDATION_ONLY"
    assert report.efficacy_validation == "NEEDS_HARDENING"
    assert report.operational_apply_complete is False
    assert by_id["execution_24h"].status in {GateStatus.PARTIAL, GateStatus.READY_FOR_REVIEW}
    assert by_id["lesson_work_linkage"].status is GateStatus.NOT_STARTED
    assert by_id["failure_feedback_loop"].status in {
        GateStatus.NOT_STARTED,
        GateStatus.CANDIDATE_EVIDENCE,
        GateStatus.READY_FOR_REVIEW,
    }
