"""Conservative mailbox maintenance without approval or execution authority."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MailboxPlan:
    deliver: tuple[Path, ...]
    archive: tuple[Path, ...]
    duplicates: tuple[Path, ...]
    invalid: tuple[Path, ...]


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _status(document: dict[str, Any]) -> str:
    return str(document.get("status") or document.get("state") or "PENDING").upper()


def _fingerprint(path: Path, document: dict[str, Any]) -> str | None:
    stable = {
        "stage": document.get("stage") or path.parent.name,
        "platform_id": document.get("platform_id"),
        "payload_digest": document.get("payload_digest"),
        "scope_digest": document.get("scope_digest"),
        "summary": document.get("summary"),
        "intent_dna": document.get("intent_dna"),
        "capability_gap": document.get("capability_gap"),
        "proposed_change": document.get("proposed_change"),
    }
    has_strong_identity = bool(
        document.get("payload_digest")
        or document.get("scope_digest")
        or (document.get("platform_id") and document.get("summary"))
        or (document.get("intent_dna") and document.get("proposed_change"))
    )
    if not has_strong_identity:
        return None
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _priority(path: Path, document: dict[str, Any]) -> tuple[int, str, str]:
    combined = " ".join(
        str(document.get(key) or "")
        for key in ("type", "stage", "assignee", "summary", "intent_dna", "capability_gap")
    ).lower()
    if "self_improvement" in combined or "self-improvement" in combined or path.parent.name == "self-improvement":
        rank = 0
    elif any(token in combined for token in ("수정", "improvement", "impediment", "#061")):
        rank = 1
    elif "beom" in combined or "범" in combined:
        rank = 2
    else:
        rank = 3
    created = str(document.get("created_at") or document.get("detected_at") or "")
    return rank, created, path.as_posix()


def build_plan(inbox_root: Path, *, batch_size: int = 30) -> MailboxPlan:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    candidates: list[tuple[Path, dict[str, Any]]] = []
    archive: list[Path] = []
    duplicates: list[Path] = []
    invalid: list[Path] = []
    seen: set[str] = set()
    for path in sorted(inbox_root.rglob("*.json")) if inbox_root.is_dir() else ():
        document = _load(path)
        if document is None:
            invalid.append(path)
            continue
        if _status(document) in {"FULFILLED", "COMPLETED", "ARCHIVED"}:
            archive.append(path)
            continue
        fingerprint = _fingerprint(path, document)
        if fingerprint is not None and fingerprint in seen:
            archive.append(path)
            duplicates.append(path)
            continue
        if fingerprint is not None:
            seen.add(fingerprint)
        candidates.append((path, document))
    candidates.sort(key=lambda item: _priority(*item))
    return MailboxPlan(
        deliver=tuple(path for path, _ in candidates[:batch_size]),
        archive=tuple(archive),
        duplicates=tuple(duplicates),
        invalid=tuple(invalid),
    )


def apply_archive(plan: MailboxPlan, *, inbox_root: Path, archive_root: Path) -> tuple[Path, ...]:
    moved: list[Path] = []
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    for source in plan.archive:
        relative = source.relative_to(inbox_root)
        target = archive_root / day / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(f"{target.stem}-{sha256(str(source).encode()).hexdigest()[:8]}{target.suffix}")
        shutil.move(str(source), str(target))
        moved.append(target)
    return tuple(moved)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry-root", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--apply-archive", action="store_true")
    arguments = parser.parse_args()
    root = arguments.foundry_root.resolve()
    plan = build_plan(root / "inbox", batch_size=arguments.batch_size)
    moved: tuple[Path, ...] = ()
    if arguments.apply_archive:
        moved = apply_archive(plan, inbox_root=root / "inbox", archive_root=root / "archive" / "mailbox")
    print(json.dumps({
        "schema_version": "apf.mailbox-maintenance-plan/v1",
        "approval_automatic": False,
        "execution_automatic": False,
        "delivery_batch_size": arguments.batch_size,
        "deliver": [str(path) for path in plan.deliver],
        "archive_candidates": [str(path) for path in plan.archive],
        "duplicates": [str(path) for path in plan.duplicates],
        "invalid": [str(path) for path in plan.invalid],
        "archived": [str(path) for path in moved],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
