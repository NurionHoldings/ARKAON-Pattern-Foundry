from hashlib import sha256

import pytest

from apf.fundamental_learning_evidence import (
    compute_trace_digest,
    failure_feedback_chain_valid,
    held_out_task_valid,
    improvement_metrics_valid,
    load_reflective_lesson,
    verify_lesson_work_trace,
)


def test_verify_lesson_work_trace_digest():
    outcome = "pass"
    payload = {
        "schema_version": "apf.lesson-work-trace/v1",
        "trace_id": "t1",
        "lesson_id": "l1",
        "work_ref": "pr-1",
        "outcome": outcome,
        "work_outcome_digest": sha256(outcome.encode()).hexdigest(),
        "recorded_at": "2026-01-01T00:00:00+00:00",
    }
    document = {**payload, "trace_digest": compute_trace_digest(payload)}
    ok, reason = verify_lesson_work_trace(document)
    assert ok and reason == "ok"


def test_failure_feedback_chain_requires_fields():
    ok, _ = failure_feedback_chain_valid(
        {
            "schema_version": "apf.failure-learning-feedback/v1",
            "failure_source_ref": "state/x.jsonl#line-1",
            "root_cause_code": "X",
            "derived_learning_task_id": "task-1",
            "independent_review_ref": "inbox/eternian-review/x.json",
        }
    )
    assert ok
    ok2, reason = failure_feedback_chain_valid({"summary": "learning failure"})
    assert not ok2 and reason == "incomplete_chain"


def test_improvement_metrics_strict():
    ok, blockers = improvement_metrics_valid(
        {
            "schema_version": "apf.improvement-recognition-metrics/v1",
            "baseline_failure_count": 10,
            "post_failure_count": 7,
            "target_failure_delta": -3,
            "safe_failure_count": 0,
            "regression_count": 0,
            "ci_commit_sha": "a" * 40,
            "ci_verified_green": True,
            "ci_run_id": "run-1",
        }
    )
    assert ok and not blockers
    ok2, blockers2 = improvement_metrics_valid(
        {"schema_version": "apf.improvement-recognition-metrics/v1", "target_failure_delta": 1}
    )
    assert not ok2 and "target_failure_delta_must_be_negative" in blockers2


def test_held_out_task_requires_execution_evidence():
    ok, reason = held_out_task_valid(
        {
            "task_id": "t1",
            "separated_from_training": True,
            "training_corpus_refs": [],
            "baseline": {"executed_at": "2026-01-01T00:00:00+00:00", "evidence_digest": "a" * 64, "failed": True},
            "post_learning": {
                "executed_at": "2026-01-02T00:00:00+00:00",
                "evidence_digest": "b" * 64,
                "score": 1.0,
            },
        },
        training_fingerprint=None,
    )
    assert ok and reason == "ok"
    bad, reason2 = held_out_task_valid(
        {"task_id": "t2", "baseline_recorded": True, "post_learning_recorded": True},
        training_fingerprint=None,
    )
    assert not bad and reason2 == "not_separated_from_training"


@pytest.mark.parametrize("changes", [
    {"baseline_failure_count": None}, {"post_failure_count": None},
    {"baseline_failure_count": -1}, {"baseline_failure_count": True},
    {"target_failure_delta": float("nan")}, {"target_failure_delta": float("-inf")},
    {"target_failure_delta": -0.5}, {"safe_failure_count": False},
    {"ci_commit_sha": "not-a-sha"}, {"ci_run_id": ""},
])
def test_metrics_reject_missing_or_nonfinite_counts_and_weak_ci_identity(changes):
    metrics = {"schema_version": "apf.improvement-recognition-metrics/v1",
               "baseline_failure_count": 10, "post_failure_count": 7,
               "target_failure_delta": -3, "safe_failure_count": 0, "regression_count": 0,
               "ci_commit_sha": "a" * 40, "ci_run_id": "run-1", "ci_verified_green": True}
    assert improvement_metrics_valid({**metrics, **changes})[0] is False


@pytest.mark.parametrize("lesson_id", ["../../outside", "/tmp/outside", "..", "a/b", "a\\b"])
def test_lesson_lookup_rejects_path_escape(tmp_path, lesson_id):
    assert load_reflective_lesson(tmp_path, lesson_id) is None
