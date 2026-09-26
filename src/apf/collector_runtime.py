from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, RLock
from typing import Protocol

from .continuous_collection import (
    CollectionCandidate,
    CollectionDecision,
    ContinuousCollectionPolicy,
    StartupTrigger,
    decide_collection,
)


class CandidateProvider(Protocol):
    def candidates(self) -> Iterable[CollectionCandidate]: ...


class ContentFetcher(Protocol):
    def fetch(self, candidate: CollectionCandidate, max_bytes: int) -> bytes: ...


class AuditSink(Protocol):
    def record(self, event: CollectionAuditEvent) -> None: ...


class ContentHashStore(Protocol):
    def claim(self, digest: str) -> bool:
        """Atomically return True only for the first claimant."""
        ...


@dataclass(frozen=True)
class CollectionAuditEvent:
    source_id: str
    locator: str
    decision: str
    collected: bool
    reusable: bool
    content_hash: str | None
    content_bytes: int
    occurred_at: datetime


@dataclass(frozen=True)
class CollectionCycleResult:
    considered: int
    collected: int
    denied: int
    duplicate: int
    failed: int = 0
    skipped_out_of_topic: int = 0


class MemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[CollectionAuditEvent] = []

    def record(self, event: CollectionAuditEvent) -> None:
        self.events.append(event)


class MemoryContentHashStore:
    def __init__(self) -> None:
        self.values: set[str] = set()
        self._lock = RLock()

    def claim(self, digest: str) -> bool:
        with self._lock:
            if digest in self.values:
                return False
            self.values.add(digest)
            return True


def load_policy(path: str | Path) -> ContinuousCollectionPolicy:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return ContinuousCollectionPolicy(
        enabled=raw["enabled"],
        startup_trigger=StartupTrigger(raw["startup_trigger"]),
        collect_immediately=raw["collect_immediately"],
        interval_seconds=raw["interval_seconds"],
        external_target_ratio=raw["external_target_ratio"],
        internal_target_ratio=raw["internal_target_ratio"],
        minimum_intent_relevance=raw["minimum_intent_relevance"],
        max_response_bytes=raw["max_response_bytes"],
    )


class CollectorRuntime:
    def __init__(
        self,
        policy: ContinuousCollectionPolicy,
        provider: CandidateProvider,
        fetcher: ContentFetcher,
        audit: AuditSink,
        *,
        clock: Callable[[], datetime] | None = None,
        content_hashes: ContentHashStore | None = None,
        topic_filter: Callable[[CollectionCandidate], bool] | None = None,
    ) -> None:
        self.policy = policy
        self.provider = provider
        self.fetcher = fetcher
        self.audit = audit
        self._clock = clock or (lambda: datetime.now(UTC))
        self._content_hashes = content_hashes or MemoryContentHashStore()
        self._topic_filter = topic_filter

    def _audit(
        self,
        candidate: CollectionCandidate,
        decision: CollectionDecision,
        *,
        content_hash: str | None = None,
        content_bytes: int = 0,
    ) -> None:
        self.audit.record(
            CollectionAuditEvent(
                source_id=candidate.source_id,
                locator=candidate.locator,
                decision=decision.reason,
                collected=decision.collect,
                reusable=decision.reusable,
                content_hash=content_hash,
                content_bytes=content_bytes,
                occurred_at=self._clock(),
            )
        )

    def run_once(self) -> CollectionCycleResult:
        considered = collected = denied = duplicate = failed = skipped_out_of_topic = 0
        for candidate in self.provider.candidates():
            if self._topic_filter is not None and not self._topic_filter(candidate):
                skipped_out_of_topic += 1
                continue
            considered += 1
            decision = decide_collection(candidate, self.policy)
            if not decision.collect:
                denied += 1
                self._audit(candidate, decision)
                continue

            try:
                payload = self.fetcher.fetch(candidate, self.policy.max_response_bytes + 1)
            except (OSError, ValueError) as exc:
                failed += 1
                self._audit(
                    candidate,
                    CollectionDecision(False, False, f"FETCH_FAILED:{type(exc).__name__}"),
                )
                continue
            if len(payload) > self.policy.max_response_bytes:
                denied += 1
                self._audit(
                    candidate,
                    CollectionDecision(False, False, "RESPONSE_TOO_LARGE"),
                    content_bytes=len(payload),
                )
                continue

            digest = hashlib.sha256(payload).hexdigest()
            if not self._content_hashes.claim(digest):
                duplicate += 1
                self._audit(
                    candidate,
                    CollectionDecision(False, False, "DUPLICATE_CONTENT"),
                    content_hash=digest,
                    content_bytes=len(payload),
                )
                continue

            collected += 1
            self._audit(candidate, decision, content_hash=digest, content_bytes=len(payload))
        return CollectionCycleResult(considered, collected, denied, duplicate, failed, skipped_out_of_topic)

    def run_forever(self, stop: Event) -> None:
        if not self.policy.enabled:
            return
        if not self.policy.collect_immediately and stop.wait(self.policy.interval_seconds):
            return
        while not stop.is_set():
            self.run_once()
            if stop.wait(self.policy.interval_seconds):
                return


def audit_event_dict(event: CollectionAuditEvent) -> dict[str, object]:
    value = asdict(event)
    value["occurred_at"] = event.occurred_at.isoformat()
    return value
