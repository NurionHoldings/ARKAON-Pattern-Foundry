#!/usr/bin/env python3
"""Assess fundamental learning improvement gates (read-only report)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apf.fundamental_learning_gates import FundamentalLearningGateAssessor  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry-root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    assessor = FundamentalLearningGateAssessor(foundry_root=args.foundry_root)
    report = assessor.assess_and_persist(dry_run=args.dry_run)
    print(json.dumps(report.to_document(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
