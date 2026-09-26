#!/usr/bin/env python3
"""CLI entry for M6 synthetic reuse proof measurement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apf.reuse_proof_measurement import (  # noqa: E402
    ReuseMeasurementRejected,
    ReuseProofMeasurementHarness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="ARKAON M6 synthetic reuse proof measurement")
    parser.add_argument("--dry-run", action="store_true", help="evaluate without writing state report")
    args = parser.parse_args()
    try:
        report = ReuseProofMeasurementHarness(foundry_root=ROOT).run(dry_run=args.dry_run)
    except ReuseMeasurementRejected as error:
        print(json.dumps({"status": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "dry_run": args.dry_run,
                "overall": report.overall.value,
                "reduction_percent": report.reduction_percent,
                "report_digest": report.report_digest,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
