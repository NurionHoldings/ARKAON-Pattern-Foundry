from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .collector_runtime import CollectionAuditEvent, audit_event_dict


class SQLiteContentHashStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS seen_content ("
                "digest TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def contains(self, digest: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM seen_content WHERE digest = ?", (digest,)
            ).fetchone()
        return row is not None

    def add(self, digest: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO seen_content(digest) VALUES (?)", (digest,)
            )


class AuditIntegrityError(ValueError):
    pass


class HashChainedJsonLinesAuditSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._previous_hash = verify_audit_log(self.path)

    def record(self, event: CollectionAuditEvent) -> None:
        payload = audit_event_dict(event)
        envelope = {"previous_hash": self._previous_hash, "event": payload}
        event_hash = _hash(envelope)
        envelope["event_hash"] = event_hash
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
        self._previous_hash = event_hash


def verify_audit_log(path: str | Path) -> str | None:
    audit_path = Path(path)
    if not audit_path.exists():
        return None
    previous_hash = None
    with audit_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                envelope = json.loads(line)
                event_hash = envelope.pop("event_hash")
            except (json.JSONDecodeError, KeyError) as exc:
                raise AuditIntegrityError(f"invalid audit record at line {line_number}") from exc
            if envelope.get("previous_hash") != previous_hash or _hash(envelope) != event_hash:
                raise AuditIntegrityError(f"broken audit chain at line {line_number}")
            previous_hash = event_hash
    return previous_hash


def _hash(value: dict[str, object]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
