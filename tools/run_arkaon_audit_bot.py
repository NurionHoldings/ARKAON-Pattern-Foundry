from __future__ import annotations

import argparse
import json
from pathlib import Path

from apf.arkaon_audit_bot import GitRevisionReader, load_change_report, run_audit, write_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the read-only ARKAON Audit Bot gate")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--approved-scope-digest", required=True)
    parser.add_argument("--approved-path", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    manifest = run_audit(
        reader=GitRevisionReader(args.repository),
        base_sha=args.base_sha,
        candidate_sha=args.candidate_sha,
        report=load_change_report(args.report),
        policy_document=policy,
        approved_scope_digest=args.approved_scope_digest,
        approved_paths=tuple(args.approved_path),
    )
    write_manifest(args.output, manifest)
    print(json.dumps(manifest.document(), sort_keys=True))
    return 0 if manifest.decision.value == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
