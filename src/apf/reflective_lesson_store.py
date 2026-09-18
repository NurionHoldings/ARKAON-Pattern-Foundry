"""Append-only persistent store for validated reflective lessons."""

from __future__ import annotations

import json
from pathlib import Path

from .reflective_learning import ReflectionRejected, ReflectiveLesson


class ReflectiveLessonStore:
    """Persists lessons under Foundry knowledge without delete or overwrite."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, lesson: ReflectiveLesson) -> Path:
        target = self.root / f"{lesson.lesson_id}.json"
        if target.exists():
            raise ReflectionRejected("lesson already recorded and cannot be overwritten")
        target.write_text(
            json.dumps(lesson.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target

    def delete(self, lesson_id: str) -> None:
        raise ReflectionRejected("failure, rejection and regression lessons cannot be deleted")

    def list_lesson_ids(self) -> tuple[str, ...]:
        return tuple(sorted(path.stem for path in self.root.glob("*.json")))
