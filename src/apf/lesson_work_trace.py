"""Append-only traces linking reflective lessons to concrete work outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path


class LessonWorkTraceRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LessonWorkTrace:
    trace_id: str
    lesson_id: str
    work_ref: str
    outcome: str
    recorded_at: datetime
    trace_digest: str

    def to_line(self) -> str:
        document = {
            "schema_version": "apf.lesson-work-trace/v1",
            "trace_id": self.trace_id,
            "lesson_id": self.lesson_id,
            "work_ref": self.work_ref,
            "outcome": self.outcome,
            "recorded_at": self.recorded_at.isoformat(),
            "trace_digest": self.trace_digest,
        }
        return json.dumps(document, ensure_ascii=False, sort_keys=True)


class LessonWorkTraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, *, lesson_id: str, work_ref: str, outcome: str, now: datetime | None = None) -> LessonWorkTrace:
        lesson_id = lesson_id.strip()
        work_ref = work_ref.strip()
        outcome = outcome.strip()
        if not lesson_id or not work_ref or not outcome:
            raise LessonWorkTraceRejected("INVALID_FIELDS")
        if len(work_ref) > 512 or len(outcome) > 2000:
            raise LessonWorkTraceRejected("FIELD_TOO_LONG")
        recorded_at = now or datetime.now(tz=UTC)
        if recorded_at.tzinfo is None:
            raise LessonWorkTraceRejected("NAIVE_TIMESTAMP")
        trace_id = sha256(f"{lesson_id}:{work_ref}:{recorded_at.isoformat()}".encode()).hexdigest()[:24]
        work_outcome_digest = sha256(outcome.encode()).hexdigest()
        payload = {
            "schema_version": "apf.lesson-work-trace/v1",
            "trace_id": trace_id,
            "lesson_id": lesson_id,
            "work_ref": work_ref,
            "outcome": outcome,
            "work_outcome_digest": work_outcome_digest,
            "recorded_at": recorded_at.isoformat(),
        }
        from .fundamental_learning_evidence import compute_trace_digest

        trace_digest = compute_trace_digest(payload)
        document = {**payload, "trace_digest": trace_digest}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")
        trace = LessonWorkTrace(trace_id, lesson_id, work_ref, outcome, recorded_at, trace_digest)
        return trace

    def list_traces(self) -> tuple[dict[str, object], ...]:
        if not self.path.is_file():
            return ()
        rows: list[dict[str, object]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return tuple(rows)
