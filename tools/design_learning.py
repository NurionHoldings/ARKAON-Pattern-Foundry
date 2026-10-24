"""Run with PYTHONPATH=src python tools/design_learning.py --baseline <40-char SHA>."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from apf.design_learning import run

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--baseline', required=True)
parser.add_argument('--write', action='store_true', help='Persist candidate report and review packets')
args = parser.parse_args()
registry = json.loads((args.root / 'config/design-learning-sources.json').read_text())
report = run(args.root, registry['sources'], args.baseline, datetime.now(UTC), dry_run=not args.write)
print(json.dumps(report, ensure_ascii=False, indent=2))
