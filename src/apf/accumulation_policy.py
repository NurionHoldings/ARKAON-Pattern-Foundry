"""ARKAON accumulation policy with bounded, owner-reviewable defaults."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AccumulationPolicyRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_optional_limit(value: Any, *, default: int | None) -> int | None:
    """Parse a limit field. None / 'unbounded' / -1 mean no cap."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {
        "unbounded",
        "none",
        "null",
        "infinite",
    }:
        return None
    if isinstance(value, (int, float)) and int(value) < 0:
        return None
    return int(value)


def has_capacity(current: int, limit: int | None) -> bool:
    return limit is None or current < limit


def remaining_capacity(current: int, limit: int | None) -> int | None:
    if limit is None:
        return None
    return max(0, limit - current)


def slice_by_limit(
    items: tuple[Any, ...] | list[Any], limit: int | None
) -> tuple[Any, ...] | list[Any]:
    if limit is None:
        return items
    return items[:limit]


@dataclass(frozen=True)
class AccumulationPolicy:
    accumulation_mode: str = "bounded"
    engine_performance_mode: str = "bounded"
    learning_memory_unbounded: bool = False
    failure_family_limit: int | None = 100
    curriculum_unbounded: bool = False
    recall_limit: int | None = 100

    @property
    def is_unbounded(self) -> bool:
        return self.accumulation_mode == "unbounded"

    @classmethod
    def load(cls, path: Path) -> AccumulationPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.accumulation-policy/v1":
            raise AccumulationPolicyRejected(
                "POLICY_SCHEMA", "unsupported accumulation policy schema"
            )
        mode = str(document.get("accumulation_mode", "bounded")).strip().lower()
        if mode not in {"unbounded", "bounded"}:
            raise AccumulationPolicyRejected(
                "ACCUMULATION_MODE", f"unsupported accumulation_mode: {mode}"
            )
        engine_mode = str(document.get("engine_performance_mode", "bounded")).strip().lower()
        if engine_mode not in {"unbounded", "bounded"}:
            raise AccumulationPolicyRejected(
                "ENGINE_MODE", f"unsupported engine_performance_mode: {engine_mode}"
            )
        raw_failure_limit = document.get("failure_family_limit")
        failure_limit: int | None
        if document.get("learning_memory_unbounded", False):
            failure_limit = None
        else:
            failure_limit = parse_optional_limit(raw_failure_limit, default=3)
        recall_limit = parse_optional_limit(document.get("recall_limit"), default=10)
        return cls(
            accumulation_mode=mode,
            engine_performance_mode=engine_mode,
            learning_memory_unbounded=bool(document.get("learning_memory_unbounded", False)),
            failure_family_limit=failure_limit,
            curriculum_unbounded=bool(document.get("curriculum_unbounded", False)),
            recall_limit=recall_limit,
        )
