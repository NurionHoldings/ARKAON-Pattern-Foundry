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
    pending: tuple[Path, ...]
    deliver: tuple[Path, ...]
    archive: tuple[Path, ...]
    duplicates: tuple[Path, ...]
    invalid: tuple[Path, ...]
    relayed: tuple[Path, ...]


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


def build_plan(
    inbox_root: Path,
    *,
    batch_size: int = 30,
    relayed_request_ids: frozenset[str] = frozenset(),
) -> MailboxPlan:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    candidates: list[tuple[Path, dict[str, Any]]] = []
    archive: list[Path] = []
    duplicates: list[Path] = []
    invalid: list[Path] = []
    relayed: list[Path] = []
    seen: set[str] = set()
    for path in sorted(inbox_root.rglob("*.json")) if inbox_root.is_dir() else ():
        document = _load(path)
        if document is None:
            invalid.append(path)
            continue
        request_id = document.get("request_id")
        if isinstance(request_id, str) and request_id in relayed_request_ids:
            archive.append(path)
            relayed.append(path)
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
    pending = tuple(path for path, _ in candidates)
    return MailboxPlan(
        pending=pending,
        deliver=pending[:batch_size],
        archive=tuple(archive),
        duplicates=tuple(duplicates),
        invalid=tuple(invalid),
        relayed=tuple(relayed),
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


def _relayed_request_ids(foundry_root: Path) -> frozenset[str]:
    state_path = foundry_root / "state" / "self-improvement-relay.json"
    document = _load(state_path)
    if document is None:
        return frozenset()
    receipts = document.get("receipts")
    if not isinstance(receipts, dict):
        return frozenset()
    return frozenset(str(request_id) for request_id in receipts)


def _plan_document(
    plan: MailboxPlan,
    *,
    batch_size: int,
    moved: tuple[Path, ...],
    summary_only: bool,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": "apf.mailbox-maintenance-plan/v1",
        "approval_automatic": False,
        "execution_automatic": False,
        "delivery_batch_size": batch_size,
        "counts": {
            "pending": len(plan.pending),
            "deliver_selected": len(plan.deliver),
            "archive_candidates": len(plan.archive),
            "duplicates": len(plan.duplicates),
            "relayed": len(plan.relayed),
            "invalid": len(plan.invalid),
            "archived": len(moved),
        },
        "deliver": [str(path) for path in plan.deliver],
    }
    if not summary_only:
        document.update(
            {
                "pending": [str(path) for path in plan.pending],
                "archive_candidates": [str(path) for path in plan.archive],
                "duplicates": [str(path) for path in plan.duplicates],
                "relayed": [str(path) for path in plan.relayed],
                "invalid": [str(path) for path in plan.invalid],
                "archived": [str(path) for path in moved],
            }
        )
    return document


def run_maintenance(
    *,
    foundry_root: Path,
    batch_size: int = 30,
    apply_archive_changes: bool = False,
    summary_only: bool = False,
    report_path: Path | None = None,
) -> dict[str, Any]:
    root = foundry_root.resolve()
    plan = build_plan(
        root / "inbox",
        batch_size=batch_size,
        relayed_request_ids=_relayed_request_ids(root),
    )
    moved: tuple[Path, ...] = ()
    if apply_archive_changes:
        moved = apply_archive(
            plan,
            inbox_root=root / "inbox",
            archive_root=root / "archive" / "mailbox",
        )
    full_document = _plan_document(
        plan,
        batch_size=batch_size,
        moved=moved,
        summary_only=False,
    )
    target = report_path or root / "state" / "mailbox-maintenance-latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(full_document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if summary_only:
        return _plan_document(
            plan,
            batch_size=batch_size,
            moved=moved,
            summary_only=True,
        )
    return full_document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry-root", type=Path, default=Path.cwd())
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--apply-archive", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--report-path", type=Path)
    arguments = parser.parse_args()
    output = run_maintenance(
        foundry_root=arguments.foundry_root,
        batch_size=arguments.batch_size,
        apply_archive_changes=arguments.apply_archive,
        summary_only=arguments.summary,
        report_path=arguments.report_path,
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
