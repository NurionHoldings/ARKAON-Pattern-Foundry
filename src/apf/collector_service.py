from __future__ import annotations

import argparse
import ipaddress
import json
import signal
import socket
import urllib.request
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit

from .collector_runtime import CollectorRuntime, load_policy
from .collector_storage import HashChainedJsonLinesAuditSink, SQLiteContentHashStore
from .continuous_collection import AssetizationBasis, CollectionCandidate
from .external_learning import SourceKind


class JsonCandidateProvider:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)

    def candidates(self):
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        for value in raw.get("sources", []):
            yield CollectionCandidate(
                source_id=value["source_id"],
                kind=SourceKind(value["kind"]),
                locator=value["locator"],
                intent_relevance=value["intent_relevance"],
                explicitly_authorized=value.get("explicitly_authorized", False),
                contains_personal_data=value.get("contains_personal_data", False),
                contains_secrets=value.get("contains_secrets", False),
                requires_credentials=value.get("requires_credentials", False),
                robots_allowed=value.get("robots_allowed", True),
                terms_allowed=value.get("terms_allowed", True),
                license_clarity=value.get("license_clarity", 0.0),
                assetization_basis=AssetizationBasis(value.get("assetization_basis", "NONE")),
                provenance_recorded=value.get("provenance_recorded", False),
                copied_source_code=value.get("copied_source_code", False),
            )


class SafeHttpsFetcher:
    def _validate_locator(self, locator: str) -> None:
        parsed = urlsplit(locator)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("only credential-free HTTPS sources are allowed")
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError("private or non-global source address blocked")

    def fetch(self, candidate: CollectionCandidate, max_bytes: int) -> bytes:
        self._validate_locator(candidate.locator)
        request = urllib.request.Request(
            candidate.locator,
            headers={"User-Agent": "ARKAON-Pattern-Foundry/0.1"},
        )
        opener = urllib.request.build_opener(_SafeRedirectHandler(self._validate_locator))
        with opener.open(request, timeout=15) as response:
            return response.read(max_bytes)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, validate_locator) -> None:
        self._validate_locator = validate_locator

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._validate_locator(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARKAON continuous collector")
    parser.add_argument("--config", required=True)
    parser.add_argument("--audit", default="arkaon-collection-audit.jsonl")
    parser.add_argument("--state", default="arkaon-collection-state.sqlite3")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    policy = load_policy(args.config)
    runtime = CollectorRuntime(
        policy,
        JsonCandidateProvider(args.config),
        SafeHttpsFetcher(),
        HashChainedJsonLinesAuditSink(args.audit),
        content_hashes=SQLiteContentHashStore(args.state),
    )
    if args.once:
        runtime.run_once()
        return 0
    stop = Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    runtime.run_forever(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
