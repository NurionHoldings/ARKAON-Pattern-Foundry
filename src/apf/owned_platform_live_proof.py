"""Harness for owned-platform live repository connection proof."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .owned_platform_connection import (
    ConnectionStatus,
    OwnedPlatformConnectionPolicy,
    OwnedPlatformConnectionRejected,
    connect_all_owned_platforms,
)


class OwnedPlatformLiveProofRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProofStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class OwnedPlatformLiveProofReport:
    foundry_root: Path
    evaluated_at: datetime
    results: tuple[dict[str, object], ...]
    overall: ProofStatus
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.owned-platform-live-proof-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "overall": self.overall.value,
            "report_digest": self.report_digest,
            "results": list(self.results),
        }


class OwnedPlatformLiveProofHarness:
    def __init__(self, *, foundry_root: Path) -> None:
        self.foundry_root = foundry_root.resolve()
        self.store_root = self.foundry_root / "state" / "owned-platform-live"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def run(self, *, now: datetime | None = None, dry_run: bool = False) -> OwnedPlatformLiveProofReport:
        evaluated_at = now or datetime.now(tz=UTC)
        if evaluated_at.tzinfo is None:
            raise OwnedPlatformLiveProofRejected("TIMESTAMP", "timezone-aware timestamp required")
        policy_path = self.foundry_root / "config" / "arkaon-owned-platform-connection.json"
        policy = OwnedPlatformConnectionPolicy.load(policy_path)
        try:
            connections = connect_all_owned_platforms(foundry_root=self.foundry_root, policy=policy)
        except OwnedPlatformConnectionRejected as error:
            raise OwnedPlatformLiveProofRejected(error.code, str(error)) from error
        results = [item.to_document() for item in connections]
        if any(item["status"] == ConnectionStatus.FAIL.value for item in results):
            overall = ProofStatus.FAIL
        elif all(item["status"] == ConnectionStatus.SKIP.value for item in results):
            overall = ProofStatus.SKIP
        else:
            overall = ProofStatus.PASS
        document = {
            "evaluated_at": evaluated_at.isoformat(),
            "foundry_root": self.foundry_root.as_posix(),
            "overall": overall.value,
            "results": results,
        }
        digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        report = OwnedPlatformLiveProofReport(
            foundry_root=self.foundry_root,
            evaluated_at=evaluated_at,
            results=tuple(results),
            overall=overall,
            report_digest=digest,
        )
        if not dry_run:
            target = self.store_root / f"{evaluated_at.strftime('%Y-%m-%d')}-{digest[:16]}.json"
            target.write_text(
                json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        if overall is ProofStatus.FAIL:
            raise OwnedPlatformLiveProofRejected("OWNED_PLATFORM_LIVE_PROOF_FAILED", "connection proof failed")
        return report
