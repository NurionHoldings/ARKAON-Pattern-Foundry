"""Relay owner-governed self-improvement inbox requests to GitHub pull requests."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from .mailbox_maintenance import run_maintenance


class RelayError(RuntimeError):
    pass


class Publisher(Protocol):
    def publish(self, *, request_id: str, scope_digest: str, content: str) -> str: ...


@dataclass(frozen=True)
class RelayReceipt:
    request_id: str
    scope_digest: str
    pull_request_url: str


@dataclass(frozen=True)
class BlockedPacket:
    source_name: str
    quarantine_name: str
    reason: str
    evidence_digest: str


@dataclass(frozen=True)
class RelayCycle:
    delivered: tuple[RelayReceipt, ...]
    blocked: tuple[BlockedPacket, ...]
    mailbox: dict[str, object]


def _canonical_scope(document: dict[str, object]) -> dict[str, object]:
    keys = (
        "request_id",
        "intent_dna",
        "capability_gap",
        "evidence_refs",
        "proposed_change",
        "expected_benefit",
        "risks",
        "validation_plan",
        "source_tier",
    )
    return {key: document[key] for key in keys}


def validate_request(document: dict[str, object]) -> tuple[str, str]:
    if document.get("schema_version") != "apf.self-improvement-request/1.0":
        raise RelayError("UNSUPPORTED_SELF_IMPROVEMENT_SCHEMA")
    if document.get("state") != "INBOX_POSTED":
        raise RelayError("INBOX_POSTED_REQUEST_REQUIRED")
    for key in (
        "production_change_allowed",
        "automatic_merge_allowed",
        "deployment_allowed",
    ):
        if document.get(key) is not False:
            raise RelayError("PROPOSE_ONLY_BOUNDARY_REQUIRED")
    request_id = document.get("request_id")
    supplied_digest = document.get("scope_digest")
    if not isinstance(request_id, str) or not request_id.strip():
        raise RelayError("REQUEST_ID_REQUIRED")
    if not isinstance(supplied_digest, str):
        raise RelayError("SCOPE_DIGEST_REQUIRED")
    try:
        scope = _canonical_scope(document)
    except KeyError as exc:
        raise RelayError("COMPLETE_SCOPE_REQUIRED") from exc
    encoded = json.dumps(
        scope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    actual_digest = sha256(encoded).hexdigest()
    if actual_digest != supplied_digest:
        raise RelayError("SCOPE_DIGEST_MISMATCH")
    return request_id, actual_digest


def _load_receipts(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "apf.self-improvement-relay-state/1.0":
        raise RelayError("RELAY_STATE_SCHEMA_INVALID")
    return dict(document.get("receipts") or {})


def _save_receipts(path: Path, receipts: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": "apf.self-improvement-relay-state/1.0",
                "receipts": receipts,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _quarantine_packet(*, foundry_root: Path, path: Path, reason: str) -> BlockedPacket:
    content = path.read_bytes()
    digest = sha256(content).hexdigest()
    quarantine = foundry_root / "quarantine" / "self-improvement"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / f"{path.stem}-{digest[:12]}.json"
    if target.exists() and target.read_bytes() != content:
        raise RelayError("QUARANTINE_DIGEST_COLLISION")
    if not target.exists():
        path.replace(target)
    else:
        path.unlink()
    receipt = {
        "schema_version": "apf.self-improvement-quarantine/1.0",
        "state": "BLOCKED",
        "source_name": path.name,
        "quarantine_name": target.name,
        "reason": reason,
        "evidence_digest": f"sha256:{digest}",
    }
    receipt_path = target.with_suffix(".blocked.json")
    temporary = receipt_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(receipt_path)
    return BlockedPacket(path.name, target.name, reason, f"sha256:{digest}")


def relay_once(
    *, foundry_root: Path, publisher: Publisher
) -> tuple[tuple[RelayReceipt, ...], tuple[BlockedPacket, ...]]:
    state_root = foundry_root / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / "self-improvement-relay.lock"
    try:
        descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RelayError("RELAY_ALREADY_RUNNING") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        inbox = foundry_root / "inbox" / "self-improvement"
        state_path = state_root / "self-improvement-relay.json"
        receipts = _load_receipts(state_path)
        delivered: list[RelayReceipt] = []
        blocked: list[BlockedPacket] = []
        for path in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(document, dict):
                    raise RelayError("SELF_IMPROVEMENT_OBJECT_REQUIRED")
                request_id, scope_digest = validate_request(document)
            except (OSError, UnicodeError, json.JSONDecodeError, RelayError) as exc:
                reason = str(exc) if isinstance(exc, RelayError) else type(exc).__name__.upper()
                blocked.append(
                    _quarantine_packet(foundry_root=foundry_root, path=path, reason=reason)
                )
                continue
            existing = receipts.get(request_id)
            if existing:
                if existing.get("scope_digest") != scope_digest:
                    blocked.append(
                        _quarantine_packet(
                            foundry_root=foundry_root,
                            path=path,
                            reason="RELAY_REQUEST_ID_SCOPE_CONFLICT",
                        )
                    )
                    continue
                continue
            content = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
            url = publisher.publish(
                request_id=request_id,
                scope_digest=scope_digest,
                content=content,
            )
            receipts[request_id] = {
                "scope_digest": scope_digest,
                "pull_request_url": url,
            }
            _save_receipts(state_path, receipts)
            delivered.append(RelayReceipt(request_id, scope_digest, url))
        return tuple(delivered), tuple(blocked)
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def relay_cycle(*, foundry_root: Path, publisher: Publisher, batch_size: int = 30) -> RelayCycle:
    delivered, blocked = relay_once(foundry_root=foundry_root, publisher=publisher)
    mailbox = run_maintenance(
        foundry_root=foundry_root,
        batch_size=batch_size,
        apply_archive_changes=True,
        summary_only=True,
    )
    return RelayCycle(delivered=delivered, blocked=blocked, mailbox=mailbox)


class GhPublisher:
    def __init__(self, repository: str) -> None:
        self.repository = repository

    def _run(self, *arguments: str, input_text: str | None = None) -> str:
        completed = subprocess.run(
            ("gh", *arguments),
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RelayError("GITHUB_RELAY_FAILED")
        return (completed.stdout or "").strip()

    def publish(self, *, request_id: str, scope_digest: str, content: str) -> str:
        self._run("auth", "status")
        owner, name = self.repository.split("/", 1)
        branch = f"arkaon/self-improvement-{request_id}"
        head_sha = self._run(
            "api",
            f"repos/{owner}/{name}/git/ref/heads/main",
            "--jq",
            ".object.sha",
        )
        encoded = base64.b64encode(content.encode()).decode()
        ref_payload = json.dumps({"ref": f"refs/heads/{branch}", "sha": head_sha})
        try:
            self._run(
                "api",
                f"repos/{owner}/{name}/git/refs",
                "--method",
                "POST",
                "--input",
                "-",
                input_text=ref_payload,
            )
        except RelayError:
            existing = self._run(
                "api",
                f"repos/{owner}/{name}/pulls?state=open&head={owner}:{branch}",
                "--jq",
                ".[0].html_url // empty",
            )
            if existing:
                return existing
            raise
        file_path = f"requests/self-improvement/{request_id}.json"
        file_payload = json.dumps(
            {
                "message": f"SELF_IMPROVEMENT_REQUEST {request_id}",
                "content": encoded,
                "branch": branch,
            }
        )
        self._run(
            "api",
            f"repos/{owner}/{name}/contents/{file_path}",
            "--method",
            "PUT",
            "--input",
            "-",
            input_text=file_payload,
        )
        body = (
            "ARKAON self-improvement request.\n\n"
            f"- request_id: `{request_id}`\n"
            f"- scope_digest: `{scope_digest}`\n"
            "- status: OWNER_APPROVAL_REQUIRED\n"
            "- automatic merge/deploy: forbidden\n"
        )
        pr_payload = json.dumps(
            {
                "title": f"SELF_IMPROVEMENT_REQUEST — {request_id}",
                "head": branch,
                "base": "main",
                "body": body,
                "draft": False,
            }
        )
        return self._run(
            "api",
            f"repos/{owner}/{name}/pulls",
            "--method",
            "POST",
            "--input",
            "-",
            "--jq",
            ".html_url",
            input_text=pr_payload,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry-root", type=Path, required=True)
    parser.add_argument(
        "--repository",
        default="NurionHoldings/ARKAON-Pattern-Foundry",
    )
    parser.add_argument("--watch-seconds", type=int, default=0)
    parser.add_argument("--mailbox-batch-size", type=int, default=30)
    arguments = parser.parse_args()
    publisher = GhPublisher(arguments.repository)
    while True:
        relay_cycle(
            foundry_root=arguments.foundry_root.resolve(),
            publisher=publisher,
            batch_size=arguments.mailbox_batch_size,
        )
        if arguments.watch_seconds <= 0:
            return 0
        time.sleep(max(arguments.watch_seconds, 5))


if __name__ == "__main__":
    raise SystemExit(main())
