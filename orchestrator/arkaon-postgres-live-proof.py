#!/usr/bin/env python3
"""CLI entry for PostgreSQL live proof harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apf.postgres_live_proof import PostgresLiveProofHarness, PostgresLiveProofRejected  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="ARKAON PostgreSQL live proof harness")
    parser.add_argument("--dry-run", action="store_true", help="evaluate without writing state report")
    args = parser.parse_args()
    try:
        report = PostgresLiveProofHarness(foundry_root=ROOT).run(dry_run=args.dry_run)
    except PostgresLiveProofRejected as error:
        print(json.dumps({"status": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "dry_run": args.dry_run,
                "overall": report.overall.value,
                "report_digest": report.report_digest,
                "results": [
                    {"check_id": item.check_id, "status": item.status.value, "message": item.message}
                    for item in report.results
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
