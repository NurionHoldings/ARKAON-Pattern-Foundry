#!/usr/bin/env python3
"""Read-only self-heal connectivity diagnostic. No public API mutation or approval."""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

def probe(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "ARKAON-readonly-diagnostic/1.0", "Accept": "application/json,text/html"})
    try:
        with urlopen(req, timeout=8) as resp:
            body = resp.read(8192)
            return {"url": url, "status": resp.status, "ok": 200 <= resp.status < 300,
                    "content_type": resp.headers.get("Content-Type", ""), "sample": body[:500].decode("utf-8", "replace")}
    except HTTPError as exc:
        return {"url": url, "status": exc.code, "ok": False, "error": "HTTP error"}
    except (URLError, TimeoutError, OSError) as exc:
        return {"url": url, "status": None, "ok": False, "error": type(exc).__name__}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="https://arkaonfoundry.netlify.app")
    parser.add_argument("--api", default=os.getenv("APF_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--output-dir", default="inbox/research")
    args = parser.parse_args()
    api = urlsplit(args.api)
    if api.scheme not in {"http", "https"} or not api.hostname:
        parser.error("--api must be an http(s) URL")
    site = args.site.rstrip("/")
    endpoints = [site + "/services/self-heal.html", site + "/services/account.html",
                 site + "/health", site + "/console", args.api.rstrip("/") + "/health",
                 args.api.rstrip("/") + "/console"]
    probes = [probe(u) for u in endpoints]
    result = {"schema": "arkaon.self-heal.diagnostic/v1",
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "READ_ONLY", "review_state": "PENDING_HUMAN_REVIEW",
              "auto_deploy": False, "probes": probes,
              "notes": ["Connectivity probes are not a functional self-heal scan.",
                        "Never enable public inbox writes without authentication, rate limits and abuse review.",
                        "No approval, release, or Intent_DNA mutation performed."]}
    dest = Path(args.output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    name = "self-heal-connectivity-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    target = dest / name
    with target.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved: {target}")
    for p in probes:
        print(f"{p['status'] or 'ERR'} {p['url']}")
    return 0 if probes[-2]["ok"] else 2

if __name__ == "__main__":
    sys.exit(main())
