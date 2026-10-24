"""Transactional lesson persistence. Hashes detect corruption, not authorship."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .learning_memory import LearningLesson, LearningMemory, LessonOutcome


class DurableLearningMemory(LearningMemory):
    """Reload under a SQLite write transaction to avoid stale-writer loss.

    Access to the database is a trusted local boundary, as is access to the
    existing in-memory API. A checksum does not replace independent review.
    """

    def __init__(self, *, path: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._database() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS learning_lessons "
                "(identity TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL)"
            )
            self._reload(database)

    @contextmanager
    def _database(self):
        database = sqlite3.connect(self.path, timeout=5)
        try:
            database.execute("PRAGMA synchronous=FULL")
            with database:
                database.execute("BEGIN IMMEDIATE")
                yield database
        finally:
            database.close()

    def _reload(self, database) -> None:
        # Validate into a temporary memory; never expose a partially read store.
        checked = LearningMemory(
            minimum_confidence=self.minimum_confidence,
            failure_family_limit=self.failure_family_limit,
        )
        for identity, payload, digest in database.execute(
            "SELECT identity, payload, digest FROM learning_lessons ORDER BY identity"
        ):
            try:
                raw = json.loads(payload)
                if raw["verified"] is not True or not isinstance(raw["evidence_refs"], list):
                    raise ValueError("INVALID_LESSON_TYPES")
                raw["evidence_refs"] = tuple(raw["evidence_refs"])
                raw["outcome"] = LessonOutcome(raw["outcome"])
                lesson = LearningLesson(**raw)
                if lesson.semantic_identity_hash != identity or lesson.content_hash != digest:
                    raise ValueError("LESSON_DIGEST_MISMATCH")
                checked.remember(lesson)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValueError("LEARNING_STORE_INVALID") from exc
        self._lessons = checked._lessons

    def _store(self, lesson: LearningLesson, *, upgrade: bool) -> str:
        with self._database() as database:
            self._reload(database)
            previous = dict(self._lessons)
            try:
                identity = (
                    super().upgrade(lesson) if upgrade else super().remember(lesson)
                )
                database.execute(
                    "INSERT INTO learning_lessons(identity, payload, digest) VALUES (?, ?, ?) "
                    "ON CONFLICT(identity) DO UPDATE SET payload=excluded.payload, digest=excluded.digest",
                    (identity, json.dumps(asdict(lesson), sort_keys=True), lesson.content_hash),
                )
            except Exception:
                self._lessons = previous
                raise
        return identity

    def remember(self, lesson: LearningLesson) -> str:
        return self._store(lesson, upgrade=False)

    def upgrade(self, lesson: LearningLesson) -> str:
        return self._store(lesson, upgrade=True)

    def recall(self, **kwargs) -> tuple[LearningLesson, ...]:
        with self._database() as database:
            self._reload(database)
            return super().recall(**kwargs)

    def __len__(self) -> int:
        with self._database() as database:
            self._reload(database)
            return super().__len__()
