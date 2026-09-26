#!/usr/bin/env python3
"""Run map ops gates with an ETA shadow observation that triggers ADVISORY."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apf.map_ops_bridge import bridge_map_ops_gate_report  # noqa: E402
from apf.map_ops_gate import EtaShadowObservation, GateStatus, MapOpsGateHarness  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Map ops ADVISORY demo")
    parser.add_argument("--dry-run", action="store_true", help="plan inbox path without writing files")
    parser.add_argument("--predicted-s", type=int, default=600)
    parser.add_argument("--observed-s", type=int, default=3600)
    args = parser.parse_args()
    now = datetime.now(tz=UTC)
    foundry_root = ROOT
    observation = EtaShadowObservation(
        route_id="demo-advisory-route",
        predicted_duration_s=args.predicted_s,
        observed_duration_s=args.observed_s,
    )
    report = MapOpsGateHarness(foundry_root=foundry_root).run(
        platform_id="ARKAON_FOUNDRY",
        now=now,
        eta_observation=observation,
    )
    run_id = f"demo-map-ops-{now.strftime('%Y%m%d%H%M%S')}"
    inbox_path = bridge_map_ops_gate_report(
        foundry_root=foundry_root,
        report=report,
        run_id=run_id,
        now=now,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "dry_run": args.dry_run,
                "overall": report.overall.value,
                "eta_delta_s": observation.delta_s,
                "inbox_path": inbox_path,
                "advisory": report.overall is GateStatus.ADVISORY,
                "gates": [
                    {"gate_id": item.gate_id, "status": item.status.value, "message": item.message}
                    for item in report.results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.overall is GateStatus.ADVISORY else 1


if __name__ == "__main__":
    raise SystemExit(main())
