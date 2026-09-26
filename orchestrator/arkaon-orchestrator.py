#!/usr/bin/env python3
"""CLI entry for the central ARKAON orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apf.central_orchestrator import (  # noqa: E402
    CentralOrchestrator,
    OrchestratorError,
    classify_inbox_packet_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Central ARKAON orchestrator")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and analyze without writing inbox, reports, logs, or state",
    )
    parser.add_argument(
        "--demo-map-ops-advisory",
        action="store_true",
        help="use demo ETA shadow (600s predicted vs 3600s observed) to trigger map ops ADVISORY",
    )
    args = parser.parse_args()

    foundry_root = Path(__file__).resolve().parents[1]
    try:
        orchestrator = CentralOrchestrator.from_config(foundry_root)
        registrations = CentralOrchestrator.load_platforms(
            foundry_root / "config" / "platforms.json",
            foundry_root=foundry_root,
        )
        report = orchestrator.run(
            registrations,
            dry_run=args.dry_run,
            demo_map_ops_advisory=args.demo_map_ops_advisory,
        )
    except OrchestratorError as error:
        print(json.dumps({"status": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"status": "error", "code": "ORCHESTRATOR_FAILURE", "message": str(error)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "dry_run": args.dry_run,
                "run_id": report.run_id,
                "platforms": len(report.platform_reports),
                "inbox_packets": len(report.inbox_packets),
                "inbox_packet_plan": [
                    {
                        "path": path,
                        "kind": classify_inbox_packet_path(path),
                    }
                    for path in report.inbox_packets
                ],
                "production_change_allowed": report.production_change_allowed,
                "platform_summaries": [
                    {
                        "platform_id": item.platform_id,
                        "stage": item.stage.value,
                        "candidate_commit": item.candidate_commit,
                        "inventory_digest": item.inventory_digest,
                        "error_code": item.error_code,
                    }
                    for item in report.platform_reports
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
