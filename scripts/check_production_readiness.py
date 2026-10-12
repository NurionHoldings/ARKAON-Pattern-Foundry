#!/usr/bin/env python3
"""Fail closed unless every declared production gate is evidenced and approved."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "ops/production-readiness.json").read_text(encoding="utf-8"))
errors = []
if manifest.get("production_public_enabled") is not True:
    errors.append("Production public access remains disabled")
gates = manifest.get("required_gates", [])
evidence = manifest.get("evidence", {})
if not gates or len(set(gates)) != len(gates):
    errors.append("Required gates must be present and unique")
for gate in gates:
    item = evidence.get(gate, {})
    if item.get("passed") is not True or not item.get("proof_url") or not item.get("verified_at"):
        errors.append(f"Gate not verified: {gate}")
for workstream in manifest.get("workstreams", []):
    if workstream.get("public_enabled") and workstream.get("status") != "verified":
        errors.append(f"Unverified workstream exposed: {workstream['id']}")
if errors:
    print("BLOCKED: production readiness checks failed")
    for error in errors:
        print(" -", error)
    sys.exit(1)
print("PASS: declared readiness evidence present (manual review still required)")
