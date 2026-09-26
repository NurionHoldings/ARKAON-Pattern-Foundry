"""Research watch registry and digest-based change detection for external observation input."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path


class ResearchWatchRejected(ValueError):
    pass


class WatchSourceKind(str, Enum):
    LOCAL_MANIFEST = "LOCAL_MANIFEST"


@dataclass(frozen=True)
class ResearchWatchPolicy:
    automatic_learning: bool = False
    production_change_allowed: bool = False
    competitor_copy_allowed: bool = False
    default_interval_seconds: int = 900

    @classmethod
    def load(cls, path: Path) -> ResearchWatchPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-research-watch/v1":
            raise ResearchWatchRejected("unsupported research watch schema")
        if (
            document.get("automatic_learning")
            or document.get("production_change_allowed")
            or document.get("competitor_copy_allowed")
        ):
            raise ResearchWatchRejected("research watch must remain research-packet only")
        return cls(
            automatic_learning=bool(document.get("automatic_learning")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            competitor_copy_allowed=bool(document.get("competitor_copy_allowed")),
            default_interval_seconds=int(document.get("default_interval_seconds", 900)),
        )


@dataclass(frozen=True)
class WatchTarget:
    watch_id: str
    kind: WatchSourceKind
    path: str
    platform_id: str
    enabled: bool = True


@dataclass(frozen=True)
class WatchEvent:
    watch_id: str
    platform_id: str
    previous_digest: str | None
    current_digest: str
    changed: bool
    observed_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.research-watch-event/v1",
            "watch_id": self.watch_id,
            "platform_id": self.platform_id,
            "previous_digest": self.previous_digest,
            "current_digest": self.current_digest,
            "changed": self.changed,
            "observed_at": self.observed_at.isoformat(),
        }


def load_watch_targets(foundry_root: Path) -> tuple[WatchTarget, ...]:
    path = foundry_root / "config" / "research-watch-sources.json"
    if not path.is_file():
        return ()
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "apf.research-watch-sources/v1":
        raise ResearchWatchRejected("unsupported research watch sources schema")
    targets: list[WatchTarget] = []
    for item in document.get("sources") or []:
        targets.append(
            WatchTarget(
                watch_id=str(item["watch_id"]),
                kind=WatchSourceKind(str(item.get("kind", WatchSourceKind.LOCAL_MANIFEST.value))),
                path=str(item["path"]),
                platform_id=str(item.get("platform_id", "ARKAON_FOUNDRY")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return tuple(targets)


def digest_file(path: Path) -> str:
    content = path.read_bytes()
    return sha256(content).hexdigest()


class ResearchWatchRegistry:
    """Tracks manifest digests and emits change events without storing competitor verbatim copies."""

    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy = ResearchWatchPolicy.load(self.foundry_root / "config" / "arkaon-research-watch.json")
        self.state_path = self.foundry_root / "state" / "research-watch" / "digests.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._digests: dict[str, str] = {}
        if self.state_path.is_file():
            document = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._digests = {str(key): str(value) for key, value in (document.get("digests") or {}).items()}

    def detect_changes(self, *, now: datetime) -> tuple[WatchEvent, ...]:
        if now.tzinfo is None:
            raise ResearchWatchRejected("timezone-aware timestamp required")
        events: list[WatchEvent] = []
        for target in load_watch_targets(self.foundry_root):
            if not target.enabled or target.kind is not WatchSourceKind.LOCAL_MANIFEST:
                continue
            manifest = self.foundry_root / target.path
            if not manifest.is_file():
                continue
            current = digest_file(manifest)
            previous = self._digests.get(target.watch_id)
            changed = previous is not None and previous != current
            if previous is None or changed:
                self._digests[target.watch_id] = current
            events.append(
                WatchEvent(
                    watch_id=target.watch_id,
                    platform_id=target.platform_id,
                    previous_digest=previous,
                    current_digest=current,
                    changed=changed or previous is None,
                    observed_at=now,
                )
            )
        self._persist()
        return tuple(events)

    def _persist(self) -> None:
        self.state_path.write_text(
            json.dumps({"digests": self._digests}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
