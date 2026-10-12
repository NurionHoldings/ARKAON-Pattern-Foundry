"""Read-only local API connectivity smoke check (no session creation).

Usage:
  python scripts/check_local_api_connectivity.py --base-url https://localhost:8443
  python scripts/check_local_api_connectivity.py --base-url https://localhost:8443 --insecure-local

The insecure option is limited to localhost/127.0.0.1 self-signed development servers.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def check(base: str, insecure_local: bool) -> int:
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        print("ERROR: expected http(s) base URL")
        return 2
    if insecure_local and (parsed.scheme != "https" or parsed.hostname not in ("localhost", "127.0.0.1", "::1")):
        print("ERROR: --insecure-local is allowed only for loopback HTTPS")
        return 2
    context = ssl._create_unverified_context() if insecure_local else ssl.create_default_context()
    results = []
    for path, expected in (("/health", {200}), ("/console", {401}), ("/v1/console/mailbox", {401})):
        url = base.rstrip("/") + path
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=8, context=context) as response:
                status = response.status
                body = response.read(4096)
        except HTTPError as exc:
            status = exc.code
            body = exc.read(4096)
        except (URLError, TimeoutError, OSError) as exc:
            results.append({"path": path, "ok": False, "error": type(exc).__name__})
            continue
        ok = status in expected
        if path == "/health" and status == 200:
            try:
                ok = json.loads(body).get("status") == "ok"
            except (ValueError, UnicodeDecodeError):
                ok = False
        results.append({"path": path, "status": status, "ok": ok})
    print(json.dumps({"base_url": base, "checks": results, "passed": all(x["ok"] for x in results)}, ensure_ascii=False, indent=2))
    return 0 if all(x["ok"] for x in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://localhost:8443")
    parser.add_argument("--insecure-local", action="store_true")
    args = parser.parse_args()
    sys.exit(check(args.base_url, args.insecure_local))
