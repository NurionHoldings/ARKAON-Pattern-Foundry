from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .domain import CRITICAL_AXES, INTENT_AXES, IntentDNA


@dataclass(frozen=True)
class IntentGate:
    ready: bool
    missing_critical_axes: tuple[str, ...]
    disputed_core_count: int
    reason: str


def canonical_payload(dna: IntentDNA) -> dict:
    axes = {}
    for axis in INTENT_AXES:
        values = dna.axes.get(axis, [])
        axes[axis] = sorted(
            [
                {
                    "text": item.canonical_text.strip(),
                    "stability": item.stability,
                    "disputed": item.disputed,
                }
                for item in values
            ],
            key=lambda row: (row["text"], row["stability"]),
        )
    return {"axes": axes}


def fingerprint(dna: IntentDNA) -> str:
    raw = json.dumps(canonical_payload(dna), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evaluate_gate(dna: IntentDNA, threshold: float = 0.85) -> IntentGate:
    missing = tuple(sorted(axis for axis in CRITICAL_AXES if not dna.axes.get(axis)))
    disputed = sum(
        1
        for axis in CRITICAL_AXES
        for statement in dna.axes.get(axis, [])
        if statement.disputed and statement.stability == "CORE"
    )
    ready = dna.completeness >= threshold and not missing and disputed == 0
    reason = "READY" if ready else "INTENT_DNA_INCOMPLETE_OR_DISPUTED"
    return IntentGate(ready, missing, disputed, reason)


def artifact_should_be_deeply_analyzed(
    *, relevance: float, content_hash_seen: bool, cached_fingerprint_match: bool
) -> bool:
    if content_hash_seen or cached_fingerprint_match:
        return False
    return relevance >= 0.30

