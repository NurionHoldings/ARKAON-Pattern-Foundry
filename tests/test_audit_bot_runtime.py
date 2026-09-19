import json
import subprocess

import pytest

from apf.arkaon_audit_bot import AuditBotError
from apf.audit_bot_runtime import enqueue_verified_change, process_audit_queue

SCOPE = "a" * 64


def git(root, *args):
    result = subprocess.run(("git", "-C", str(root), *args), check=True, capture_output=True, text=True)
    return result.stdout.strip()


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def prepare_repository(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.email", "test@example.com")
    git(repository, "config", "user.name", "test")
    (repository / "README.md").write_text("base", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "base")
    base = git(repository, "rev-parse", "HEAD")
    (repository / "docs").mkdir()
    (repository / "docs" / "safe.md").write_text("safe", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "candidate")
    return repository, base, git(repository, "rev-parse", "HEAD")


def prepare_foundry(tmp_path, base, candidate):
    root = tmp_path / "foundry"
    request_id = "audit-runtime-001"
    receipt = "b" * 64
    source_commit = "c" * 40
    write_json(
        root / "config/audit.json",
        {
            "schema_version": "apf.arkaon-audit-policy/1.0",
            "protected_paths": ["src/apf/self_improvement_relay.py"],
            "bounded_keys": ["max_runtime_seconds"],
            "portable_path_keys": ["foundry_root"],
            "intent_sensitive_prefixes": ["src/apf/", "config/"],
        },
    )
    write_json(
        root / "state/owner-approvals.json",
        {
            "schema_version": "apf.owner-approval-ledger/1.0",
            "entries": [
                {
                    "request_id": request_id,
                    "scope_digest": SCOPE,
                    "receipt_digest": receipt,
                    "source_commit_sha": source_commit,
                    "allowed_paths": ["docs"],
                }
            ],
        },
    )
    write_json(
        root / f"state/self-improvement-execution-queue/{request_id}.json",
        {
            "schema_version": "apf.approved-execution-job/1.0",
            "state": "OWNER_APPROVED",
            "request_id": request_id,
            "scope_digest": SCOPE,
            "receipt_digest": receipt,
            "source_commit_sha": source_commit,
        },
    )
    write_json(
        root / "state/change-reports/report.json",
        {
            "schema_version": "apf.arkaon-change-report/1.0",
            "request_id": request_id,
            "scope_digest": SCOPE,
            "reported_changed_paths": ["docs/safe.md"],
            "intent_dna_refs": [],
            "test_evidence_sha256": ["sha256:" + "d" * 64],
        },
    )
    job = {
        "schema_version": "apf.arkaon-audit-job/1.0",
        "state": "ARKAON_VERIFIED",
        "request_id": request_id,
        "scope_digest": SCOPE,
        "base_sha": base,
        "candidate_sha": candidate,
        "change_report_path": "state/change-reports/report.json",
        "arkaon_test_evidence_digest": "sha256:" + "e" * 64,
        "merge_allowed": False,
        "deployment_allowed": False,
    }
    write_json(root / f"state/self-improvement-audit-queue/{request_id}.json", job)
    return root, request_id


def test_arkaon_verification_enqueue_is_atomic_and_conflict_safe(tmp_path):
    root = tmp_path / "foundry"
    arguments = {
        "foundry_root": root,
        "request_id": "audit-runtime-001",
        "scope_digest": SCOPE,
        "base_sha": "b" * 40,
        "candidate_sha": "c" * 40,
        "change_report_path": "state/change-reports/report.json",
        "arkaon_test_evidence_digest": "sha256:" + "d" * 64,
    }
    first = enqueue_verified_change(**arguments)
    second = enqueue_verified_change(**arguments)
    assert first == second
    arguments["candidate_sha"] = "e" * 40
    with pytest.raises(AuditBotError, match="AUDIT_JOB_CONFLICT"):
        enqueue_verified_change(**arguments)


def test_runtime_binds_approval_runs_audit_and_stops_for_eternian(tmp_path):
    repository, base, candidate = prepare_repository(tmp_path)
    root, request_id = prepare_foundry(tmp_path, base, candidate)

    result = process_audit_queue(
        foundry_root=root,
        repository_root=repository,
        policy_path=root / "config/audit.json",
    )

    assert result.passed == (request_id,)
    job = json.loads(
        (root / f"state/self-improvement-audit-queue/{request_id}.json").read_text()
    )
    assert job["state"] == "ETERNIAN_AUDIT_REQUIRED"
    assert job["merge_allowed"] is job["deployment_allowed"] is False
    manifest = json.loads((root / f"state/audit-manifests/{request_id}.json").read_text())
    assert manifest["decision"] == "PASS"
    assert manifest["merge_allowed"] is manifest["deployment_allowed"] is False


def test_corrupt_job_is_quarantined_and_later_valid_job_continues(tmp_path):
    repository, base, candidate = prepare_repository(tmp_path)
    root, request_id = prepare_foundry(tmp_path, base, candidate)
    queue = root / "state/self-improvement-audit-queue"
    valid = queue / f"{request_id}.json"
    valid.replace(queue / "100-valid.json")
    (queue / "000-corrupt.json").write_text("{broken", encoding="utf-8")

    result = process_audit_queue(
        foundry_root=root,
        repository_root=repository,
        policy_path=root / "config/audit.json",
    )

    assert result.passed == (request_id,)
    assert result.blocked == ("000-corrupt",)
    assert list((root / "quarantine/audit-bot").glob("000-corrupt-*.blocked.json"))


def test_missing_approval_binding_blocks_without_manifest(tmp_path):
    repository, base, candidate = prepare_repository(tmp_path)
    root, request_id = prepare_foundry(tmp_path, base, candidate)
    (root / "state/owner-approvals.json").unlink()

    result = process_audit_queue(
        foundry_root=root,
        repository_root=repository,
        policy_path=root / "config/audit.json",
    )

    assert result.blocked == (request_id,)
    assert not (root / f"state/audit-manifests/{request_id}.json").exists()
