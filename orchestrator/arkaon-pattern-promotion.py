#!/usr/bin/env python3
"""CLI entry for pattern catalog validation and external promotion verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apf.pattern_promotion_runner import PatternPromotionRunner, PromotionRunnerRejected  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="ARKAON pattern promotion and reuse proof runner")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate catalog and manifest without writing state reports",
    )
    args = parser.parse_args()
    foundry_root = ROOT
    try:
        report = PatternPromotionRunner(foundry_root=foundry_root).run(dry_run=args.dry_run)
    except PromotionRunnerRejected as error:
        print(json.dumps({"status": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"status": "error", "code": "PROMOTION_RUNNER_FAILURE", "message": str(error)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "dry_run": args.dry_run,
                "catalog_revision": report.catalog_revision,
                "candidate_count": report.candidate_count,
                "verified_count": report.verified_count,
                "pending_count": report.pending_count,
                "rejected_count": report.rejected_count,
                "reuse_proof_ready": report.reuse_proof is not None,
                "reuse_proof": report.reuse_proof,
                "report_digest": report.report_digest,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
