"""Fail-closed command line management for Audit Bot deployment baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apf.arkaon_audit_bot import AuditBotError, AuditDecision
from apf.audit_bot_internal import (
    activate_deployment_baseline_from_receipt,
    create_deployment_baseline,
    persist_deployment_baseline,
    run_internal_integrity_audit,
)


def _object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditBotError("DEPLOYMENT_BASELINE_INPUT_INVALID") from exc
    if not isinstance(value, dict):
        raise AuditBotError("DEPLOYMENT_BASELINE_INPUT_INVALID")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    candidate = commands.add_parser("candidate")
    candidate.add_argument("--repository-root", type=Path, required=True)
    candidate.add_argument("--policy", type=Path, required=True)
    candidate.add_argument("--commit-sha", required=True)
    candidate.add_argument("--output", type=Path, required=True)

    activate = commands.add_parser("activate")
    activate.add_argument("--candidate", type=Path, required=True)
    activate.add_argument("--approval-receipt", type=Path, required=True)
    activate.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--foundry-root", type=Path, required=True)
    verify.add_argument("--repository-root", type=Path, required=True)
    verify.add_argument("--policy", type=Path, required=True)
    verify.add_argument("--baseline", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "candidate":
            document = create_deployment_baseline(
                repository_root=args.repository_root.resolve(),
                policy_path=args.policy.resolve(),
                deployed_commit_sha=args.commit_sha,
            )
            persist_deployment_baseline(args.output.resolve(), document)
            result = document
        elif args.command == "activate":
            result = activate_deployment_baseline_from_receipt(
                _object(args.candidate.resolve()), _object(args.approval_receipt.resolve())
            )
            persist_deployment_baseline(args.output.resolve(), result)
        else:
            audit = run_internal_integrity_audit(
                foundry_root=args.foundry_root.resolve(),
                repository_root=args.repository_root.resolve(),
                policy_path=args.policy.resolve(),
                baseline_path=args.baseline.resolve(),
            )
            result = {
                "decision": audit.decision.value,
                "findings": audit.findings,
                "evidence_digest": audit.evidence_digest,
            }
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if audit.decision is AuditDecision.PASS else 2
    except AuditBotError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
