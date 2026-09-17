"""Relay owner-governed self-improvement inbox requests to GitHub pull requests."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol


class RelayError(RuntimeError):
    pass


class Publisher(Protocol):
    def publish(self, *, request_id: str, scope_digest: str, content: str) -> str: ...


@dataclass(frozen=True)
class RelayReceipt:
    request_id: str
    scope_digest: str
    pull_request_url: str


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


def relay_once(*, foundry_root: Path, publisher: Publisher) -> tuple[RelayReceipt, ...]:
    inbox = foundry_root / "inbox" / "self-improvement"
    state_path = foundry_root / "state" / "self-improvement-relay.json"
    receipts = _load_receipts(state_path)
    delivered: list[RelayReceipt] = []
    for path in sorted(inbox.glob("*.json")) if inbox.is_dir() else ():
        document = json.loads(path.read_text(encoding="utf-8"))
        request_id, scope_digest = validate_request(document)
        existing = receipts.get(request_id)
        if existing:
            if existing.get("scope_digest") != scope_digest:
                raise RelayError("RELAY_REQUEST_ID_SCOPE_CONFLICT")
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
    return tuple(delivered)


class GhPublisher:
    def __init__(self, repository: str) -> None:
        self.repository = repository

    def _run(self, *arguments: str, input_text: str | None = None) -> str:
        completed = subprocess.run(
            ("gh", *arguments),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RelayError("GITHUB_RELAY_FAILED")
        return completed.stdout.strip()

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
            f"- request_id: \`{request_id}\`\n"
            f"- scope_digest: \`{scope_digest}\`\n"
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
    arguments = parser.parse_args()
    publisher = GhPublisher(arguments.repository)
    while True:
        relay_once(foundry_root=arguments.foundry_root.resolve(), publisher=publisher)
        if arguments.watch_seconds <= 0:
            return 0
        time.sleep(max(arguments.watch_seconds, 5))


if __name__ == "__main__":
    raise SystemExit(main())
