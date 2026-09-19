import json
import subprocess
from hashlib import sha256

import pytest

from apf.arkaon_audit_bot import AuditBotError, AuditDecision
from apf.audit_bot_internal import (
    activate_deployment_baseline,
    activate_deployment_baseline_from_receipt,
    create_deployment_baseline,
    persist_deployment_baseline,
    run_internal_integrity_audit,
)


def git(root, *args):
    return subprocess.run(
        ("git", "-C", str(root), *args), check=True, capture_output=True, text=True
    ).stdout.strip()


def setup(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.email", "test@example.com")
    git(repository, "config", "user.name", "test")
    protected = repository / "control.py"
    protected.write_text("safe", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "deployed")
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": "apf.arkaon-audit-policy/1.0",
                "protected_paths": ["control.py"],
                "bounded_keys": ["max_runtime_seconds"],
                "portable_path_keys": ["foundry_root"],
                "intent_sensitive_prefixes": ["src/"],
            }
        ),
        encoding="utf-8",
    )
    foundry = tmp_path / "foundry"
    foundry.mkdir()
    baseline_path = foundry / "state/baseline.json"
    baseline_path.parent.mkdir()
    baseline = create_deployment_baseline(
        repository_root=repository,
        policy_path=policy,
        deployed_commit_sha=git(repository, "rev-parse", "HEAD"),
    )
    active = activate_deployment_baseline(
        baseline,
        approver="최인석",
        approved_at="2026-09-19T12:00:00+09:00",
        deployment_approval_digest="sha256:" + "a" * 64,
    )
    baseline_path.write_text(json.dumps(active), encoding="utf-8")
    return repository, protected, policy, foundry, baseline_path


def audit(repository, policy, foundry, baseline_path):
    return run_internal_integrity_audit(
        foundry_root=foundry,
        repository_root=repository,
        policy_path=policy,
        baseline_path=baseline_path,
    )


def test_matching_deployment_baseline_passes(tmp_path):
    repository, _, policy, foundry, baseline_path = setup(tmp_path)
    result = audit(repository, policy, foundry, baseline_path)
    assert result.decision == AuditDecision.PASS
    assert result.findings == ()


def test_protected_worktree_drift_is_blocked_in_realtime(tmp_path):
    repository, protected, policy, foundry, baseline_path = setup(tmp_path)
    protected.write_text("tampered", encoding="utf-8")
    result = audit(repository, policy, foundry, baseline_path)
    assert result.decision == AuditDecision.BLOCKED
    assert any("PROTECTED_FILE_DRIFT" in finding for finding in result.findings)


def test_missing_baseline_holds_and_duplicate_owner_ledger_blocks(tmp_path):
    repository, _, policy, foundry, baseline_path = setup(tmp_path)
    baseline_path.unlink()
    result = audit(repository, policy, foundry, baseline_path)
    assert result.decision == AuditDecision.HOLD

    ledger = foundry / "state/owner-approvals.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": "apf.owner-approval-ledger/1.0",
                "entries": [{"request_id": "same"}, {"request_id": "same"}],
            }
        ),
        encoding="utf-8",
    )
    result = audit(repository, policy, foundry, baseline_path)
    assert result.decision == AuditDecision.BLOCKED
    assert any("OWNER_APPROVAL_LEDGER_DUPLICATE" in finding for finding in result.findings)


def test_candidate_is_bound_to_current_head(tmp_path):
    repository, _, policy, _, _ = setup(tmp_path)
    with pytest.raises(AuditBotError, match="DEPLOYMENT_BASELINE_HEAD_MISMATCH"):
        create_deployment_baseline(
            repository_root=repository,
            policy_path=policy,
            deployed_commit_sha="a" * 40,
        )


def test_receipt_activation_and_exclusive_durable_persistence(tmp_path):
    repository, _, policy, _, _ = setup(tmp_path)
    candidate = create_deployment_baseline(
        repository_root=repository,
        policy_path=policy,
        deployed_commit_sha=git(repository, "rev-parse", "HEAD"),
    )
    unsigned = {
        "schema_version": "apf.deployment-approval-receipt/1.0",
        "decision": "APPROVED",
        "baseline_digest": candidate["baseline_digest"],
        "approver": "최인석",
        "approved_at": "2026-09-19T12:00:00+09:00",
    }
    digest = "sha256:" + sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    active = activate_deployment_baseline_from_receipt(
        candidate, {**unsigned, "receipt_digest": digest}
    )
    assert active["state"] == "ACTIVE"
    assert active["deployment_approval_digest"] == digest

    output = tmp_path / "state" / "baseline.json"
    persist_deployment_baseline(output, active)
    assert json.loads(output.read_text(encoding="utf-8")) == active
    with pytest.raises(AuditBotError, match="DEPLOYMENT_BASELINE_ALREADY_EXISTS"):
        persist_deployment_baseline(output, active)


def test_receipt_for_another_candidate_is_rejected(tmp_path):
    repository, _, policy, _, _ = setup(tmp_path)
    candidate = create_deployment_baseline(
        repository_root=repository,
        policy_path=policy,
        deployed_commit_sha=git(repository, "rev-parse", "HEAD"),
    )
    receipt = {
        "schema_version": "apf.deployment-approval-receipt/1.0",
        "decision": "APPROVED",
        "baseline_digest": "sha256:" + "0" * 64,
        "approver": "최인석",
        "approved_at": "2026-09-19T12:00:00+09:00",
    }
    receipt["receipt_digest"] = "sha256:" + sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(AuditBotError, match="DEPLOYMENT_APPROVAL_RECEIPT_INVALID"):
        activate_deployment_baseline_from_receipt(candidate, receipt)
