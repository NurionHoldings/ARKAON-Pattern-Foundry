#!/usr/bin/env python3
"""Read-only same-origin Foundry connectivity checks for the Netlify static site."""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONSOLE_OK = frozenset({200, 302, 401})


def probe(url: str) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json,text/html", "User-Agent": "ARKAON-site-connectivity/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            body = response.read(2048)
            sample = body.decode("utf-8", "replace")[:240]
            return {
                "url": url,
                "status": response.status,
                "ok": response.status == 200,
                "sample": sample,
            }
    except HTTPError as exc:
        body = exc.read(2048).decode("utf-8", "replace")[:240]
        status = exc.code
        ok = status == 200
        if url.rstrip("/").endswith("/console"):
            ok = status in CONSOLE_OK
        if url.rstrip("/").endswith("/health") and status == 503:
            ok = False
        return {"url": url, "status": status, "ok": ok, "sample": body}
    except (URLError, TimeoutError, OSError) as exc:
        return {"url": url, "status": None, "ok": False, "error": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="https://arkaonfoundry.netlify.app")
    args = parser.parse_args()
    base = args.site.rstrip("/")
    checks = [
        probe(f"{base}/health"),
        probe(f"{base}/console"),
    ]
    document = {
        "schema_version": "apf.site-foundry-connectivity/v1",
        "site": base,
        "checks": checks,
        "passed": all(item.get("ok") for item in checks),
        "notes": [
            "503 on /health usually means APF_API_ORIGIN is unset on Netlify Functions.",
            "404 on /health means the foundry proxy is not deployed on this site branch.",
        ],
    }
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if document["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
