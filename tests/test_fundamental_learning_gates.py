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
    report = assessor.assess(now=datetime.now(tz=UTC))
    by_id = {stage.stage_id: stage for stage in report.stages}
    assert report.overall_status == "MEMORY_FOUNDATION_ONLY"
    assert report.operational_apply_complete is False
    assert by_id["lesson_work_linkage"].status is GateStatus.NOT_STARTED
    assert by_id["held_out_comparison"].status is GateStatus.NOT_STARTED
