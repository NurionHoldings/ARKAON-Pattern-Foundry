"""Strict evidence parsers for fundamental learning gate assessment."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .reflective_learning import Decision


def parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        return ()
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_no} invalid json") from exc
        if isinstance(document, dict):
            rows.append(document)
    return tuple(rows)


def iter_hourly_learning_records(foundry_root: Path) -> tuple[dict[str, Any], ...]:
    directory = foundry_root / "state" / "hourly-learning"
    if not directory.is_dir():
        return ()
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")):
        records.extend(load_jsonl(path))
    return tuple(records)


def hourly_record_observed_at(record: dict[str, Any]) -> datetime | None:
    topic = record.get("topic")
    if not isinstance(topic, dict):
        return None
    return parse_iso_datetime(topic.get("observed_at"))


def expected_schedule_hours(schedule_path: Path, *, window_start: datetime, window_end: datetime) -> set[tuple[str, int]]:
    if not schedule_path.is_file():
        return set()
    document = json.loads(schedule_path.read_text(encoding="utf-8"))
    timezone = str(document.get("timezone", "UTC"))
    if document.get("enabled") is False:
        return set()
    tz = ZoneInfo(timezone)
    from datetime import timedelta

    expected: set[tuple[str, int]] = set()
    cursor = window_start.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    end_local = window_end.astimezone(tz)
    while cursor <= end_local:
        expected.add((cursor.strftime("%Y-%m-%d"), cursor.hour))
        cursor += timedelta(hours=1)
    return expected


def compute_trace_digest(payload: dict[str, object]) -> str:
    body = {key: value for key, value in payload.items() if key != "trace_digest"}
    return sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def verify_lesson_work_trace(document: dict[str, Any]) -> tuple[bool, str]:
    if document.get("schema_version") != "apf.lesson-work-trace/v1":
        return False, "schema"
    stored = document.get("trace_digest")
    if not isinstance(stored, str):
        return False, "missing_digest"
    expected = compute_trace_digest(document)
    if stored != expected:
        return False, "digest_mismatch"
    outcome = document.get("outcome")
    outcome_digest = document.get("work_outcome_digest")
    if isinstance(outcome, str) and isinstance(outcome_digest, str):
        if sha256(outcome.encode()).hexdigest() != outcome_digest:
            return False, "outcome_digest_mismatch"
    elif outcome_digest is not None:
        return False, "outcome_digest_without_outcome"
    return True, "ok"


def load_reflective_lesson(foundry_root: Path, lesson_id: str) -> dict[str, Any] | None:
    path = foundry_root / "knowledge" / "reflective-lessons" / f"{lesson_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def lesson_is_verified_for_linkage(lesson: dict[str, Any]) -> bool:
    outcome = lesson.get("outcome")
    if outcome != Decision.ACCEPT.value:
        return False
    if not isinstance(lesson.get("evidence_digest"), str):
        return False
    return bool(lesson.get("immutable", True))


def held_out_task_valid(item: dict[str, Any], *, training_fingerprint: str | None) -> tuple[bool, str]:
    task_id = item.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return False, "missing_task_id"
    if item.get("separated_from_training") is not True:
        return False, "not_separated_from_training"
    training_refs = item.get("training_corpus_refs", [])
    if isinstance(training_refs, list) and training_refs:
        return False, "training_corpus_refs_must_be_empty"
    if training_fingerprint and item.get("training_corpus_fingerprint") == training_fingerprint:
        return False, "matches_training_fingerprint"
    for phase in ("baseline", "post_learning"):
        block = item.get(phase)
        if not isinstance(block, dict):
            return False, f"missing_{phase}"
        if not parse_iso_datetime(block.get("executed_at")):
            return False, f"{phase}_executed_at"
        if not isinstance(block.get("evidence_digest"), str) or len(block["evidence_digest"]) != 64:
            return False, f"{phase}_evidence_digest"
        if block.get("scoring_artifact_ref") is None and block.get("score") is None and block.get("failed") is None:
            return False, f"{phase}_scoring"
    return True, "ok"


def improvement_metrics_valid(document: dict[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if document.get("schema_version") != "apf.improvement-recognition-metrics/v1":
        return False, ["schema_version"]
    delta = document.get("target_failure_delta")
    if not isinstance(delta, (int, float)) or delta >= 0:
        blockers.append("target_failure_delta_must_be_negative")
    if document.get("safe_failure_count", -1) != 0:
        blockers.append("safe_failure_count_must_be_zero")
    if document.get("regression_count", -1) != 0:
        blockers.append("regression_count_must_be_zero")
    baseline = document.get("baseline_failure_count")
    post = document.get("post_failure_count")
    if (
        isinstance(baseline, (int, float))
        and isinstance(post, (int, float))
        and isinstance(delta, (int, float))
        and int(baseline) + int(delta) != int(post)
    ):
        blockers.append("failure_counts_inconsistent_with_delta")
    ci_sha = document.get("ci_commit_sha")
    if not isinstance(ci_sha, str) or len(ci_sha) < 7:
        blockers.append("ci_commit_sha_required")
    if document.get("ci_verified_green") is not True:
        blockers.append("ci_verified_green_required")
    if not isinstance(document.get("ci_run_id"), str):
        blockers.append("ci_run_id_required")
    return len(blockers) == 0, blockers


def failure_feedback_chain_valid(document: dict[str, Any]) -> tuple[bool, str]:
    schema = document.get("schema_version", "")
    if schema == "apf.failure-learning-feedback/v1":
        required = (
            "failure_source_ref",
            "root_cause_code",
            "derived_learning_task_id",
            "independent_review_ref",
        )
        for key in required:
            if not isinstance(document.get(key), str) or not str(document[key]).strip():
                return False, f"missing_{key}"
        review = str(document["independent_review_ref"])
        if "eternian-review" not in review and "operator-decision" not in review:
            return False, "independent_review_ref_path"
        return True, "ok"
    failure_source = document.get("failure_source_ref") or document.get("source_failure_ref")
    root_cause = document.get("root_cause_code") or document.get("root_cause_summary")
    task_id = document.get("derived_learning_task_id") or document.get("learning_task_id")
    review_ref = document.get("independent_review_ref") or document.get("eternian_review_ref")
    if all(isinstance(value, str) and value.strip() for value in (failure_source, root_cause, task_id, review_ref)):
        return True, "inline_chain"
    return False, "incomplete_chain"
