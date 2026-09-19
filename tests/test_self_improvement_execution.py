import json
import subprocess

import pytest

from apf.self_improvement_execution import (
    ApprovalExecutionError,
    GhApprovalSource,
    parse_approval_receipt,
    record_approval,
    run_in_approved_worktree,
    sync_approval_receipts,
)

SCOPE = "a" * 64
COMMIT = "b" * 40


def receipt_document(**changes):
    value = {
        "schema_version": "apf.owner-approval-receipt/1.0",
        "state": "OWNER_APPROVED",
        "request_id": "relay-quarantine-001",
        "scope_digest": SCOPE,
        "approver": "최인석",
        "approved_at": "2026-09-18T23:00:00+09:00",
        "allowed_paths": ["src/apf/self_improvement_relay.py", "tests"],
        "allowed_operations": ["WRITE_WORKTREE", "RUN_TESTS"],
    }
    value.update(changes)
    return value


def test_receipt_is_bound_and_recorded_idempotently(tmp_path):
    receipt = parse_approval_receipt(receipt_document(), source_commit_sha=COMMIT)
    ledger = tmp_path / "state" / "owner-approvals.json"

    first = record_approval(
        ledger_path=ledger,
        receipt=receipt,
        expected_request_id=receipt.request_id,
        expected_scope_digest=SCOPE,
    )
    second = record_approval(
        ledger_path=ledger,
        receipt=receipt,
        expected_request_id=receipt.request_id,
        expected_scope_digest=SCOPE,
    )

    assert first == second == receipt.digest()
    assert len(json.loads(ledger.read_text(encoding="utf-8"))["entries"]) == 1


def test_approval_ledger_rejects_concurrent_writer(tmp_path):
    receipt = parse_approval_receipt(receipt_document(), source_commit_sha=COMMIT)
    ledger = tmp_path / "state" / "owner-approvals.json"
    ledger.parent.mkdir(parents=True)
    ledger.with_suffix(".json.lock").write_text("busy", encoding="utf-8")

    with pytest.raises(ApprovalExecutionError, match="APPROVAL_LEDGER_BUSY"):
        record_approval(
            ledger_path=ledger,
            receipt=receipt,
            expected_request_id=receipt.request_id,
            expected_scope_digest=SCOPE,
        )


def test_receipt_rejects_scope_or_path_tampering(tmp_path):
    receipt = parse_approval_receipt(receipt_document(), source_commit_sha=COMMIT)
    with pytest.raises(ApprovalExecutionError, match="APPROVAL_SCOPE_BINDING_MISMATCH"):
        record_approval(
            ledger_path=tmp_path / "ledger.json",
            receipt=receipt,
            expected_request_id=receipt.request_id,
            expected_scope_digest="c" * 64,
        )
    with pytest.raises(ApprovalExecutionError, match="UNSAFE_APPROVED_PATH"):
        parse_approval_receipt(
            receipt_document(allowed_paths=["../outside"]), source_commit_sha=COMMIT
        )
    with pytest.raises(ApprovalExecutionError, match="APPROVAL_SOURCE_COMMIT_INVALID"):
        parse_approval_receipt(receipt_document(), source_commit_sha="b" * 39)


def test_runner_creates_detached_worktree_and_runs_allowlisted_command(tmp_path, monkeypatch):
    receipt = parse_approval_receipt(receipt_document(), source_commit_sha=COMMIT)
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((tuple(arguments), kwargs))
        return subprocess.CompletedProcess(arguments, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_in_approved_worktree(
        repository_root=tmp_path / "repo",
        worktrees_root=tmp_path / "worktrees",
        receipt=receipt,
        expected_scope_digest=SCOPE,
        base_sha=COMMIT,
        command=("pytest", "tests/test_self_improvement_relay.py"),
    )

    assert result.returncode == 0
    assert result.receipt_digest == receipt.digest()
    assert calls[-1][0][0] == "pytest"


def test_runner_denies_unapproved_command_and_operation(tmp_path):
    receipt = parse_approval_receipt(receipt_document(), source_commit_sha=COMMIT)
    with pytest.raises(ApprovalExecutionError, match="COMMAND_NOT_ALLOWLISTED"):
        run_in_approved_worktree(
            repository_root=tmp_path,
            worktrees_root=tmp_path / "worktrees",
            receipt=receipt,
            expected_scope_digest=SCOPE,
            base_sha=COMMIT,
            command=("powershell", "anything.ps1"),
        )
    no_tests = parse_approval_receipt(
        receipt_document(allowed_operations=["WRITE_WORKTREE"]), source_commit_sha=COMMIT
    )
    with pytest.raises(ApprovalExecutionError, match="RUN_TESTS_NOT_APPROVED"):
        run_in_approved_worktree(
            repository_root=tmp_path,
            worktrees_root=tmp_path / "worktrees",
            receipt=no_tests,
            expected_scope_digest=SCOPE,
            base_sha=COMMIT,
            command=("pytest",),
        )


def test_github_receipt_content_is_fetched_at_resolved_commit(monkeypatch):
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append(tuple(arguments))
        if "commits" in arguments[2]:
            return subprocess.CompletedProcess(arguments, 0, stdout=COMMIT + "\n", stderr="")
        return subprocess.CompletedProcess(
            arguments, 0, stdout=json.dumps(receipt_document()), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    document, commit = GhApprovalSource("owner/repo").fetch("relay-quarantine-001")

    assert document["request_id"] == "relay-quarantine-001"
    assert commit == COMMIT
    assert f"ref={COMMIT}" in calls[1]


class FakeApprovalSource:
    def __init__(self, documents):
        self.documents = documents

    def fetch(self, request_id):
        value = self.documents[request_id]
        if isinstance(value, Exception):
            raise value
        return value, COMMIT


def test_approval_sync_accepts_exact_scope_and_creates_nonexecuting_queue(tmp_path):
    source = FakeApprovalSource({"relay-quarantine-001": receipt_document()})

    result = sync_approval_receipts(
        foundry_root=tmp_path,
        source=source,
        requests={"relay-quarantine-001": SCOPE},
    )

    assert len(result.accepted) == 1
    assert result.pending == result.blocked == ()
    queued = json.loads(
        (tmp_path / "state/self-improvement-execution-queue/relay-quarantine-001.json").read_text()
    )
    assert queued["state"] == "OWNER_APPROVED"
    status = json.loads((tmp_path / "state/self-improvement-approval-sync-latest.json").read_text())
    assert status["execution_automatic"] is False
    assert status["deployment_automatic"] is False


def test_approval_sync_distinguishes_pending_from_blocked(tmp_path):
    source = FakeApprovalSource(
        {
            "pending": ApprovalExecutionError("GITHUB_APPROVAL_COMMIT_UNRESOLVED"),
            "blocked": receipt_document(request_id="blocked", scope_digest="c" * 64),
        }
    )

    result = sync_approval_receipts(
        foundry_root=tmp_path,
        source=source,
        requests={"pending": SCOPE, "blocked": SCOPE},
    )

    assert result.pending == ("pending",)
    assert result.blocked == (("blocked", "APPROVAL_SCOPE_BINDING_MISMATCH"),)
    assert not (tmp_path / "state/self-improvement-execution-queue/blocked.json").exists()


def test_approval_sync_is_idempotent_and_detects_queue_conflict(tmp_path):
    source = FakeApprovalSource({"relay-quarantine-001": receipt_document()})
    first = sync_approval_receipts(
        foundry_root=tmp_path,
        source=source,
        requests={"relay-quarantine-001": SCOPE},
    )
    second = sync_approval_receipts(
        foundry_root=tmp_path,
        source=source,
        requests={"relay-quarantine-001": SCOPE},
    )
    assert len(first.accepted) == 1
    assert second.accepted == second.pending == second.blocked == ()

    queue = tmp_path / "state/self-improvement-execution-queue/relay-quarantine-001.json"
    document = json.loads(queue.read_text())
    document["scope_digest"] = "d" * 64
    queue.write_text(json.dumps(document))
    conflict = sync_approval_receipts(
        foundry_root=tmp_path,
        source=source,
        requests={"relay-quarantine-001": SCOPE},
    )
    assert conflict.blocked == (("relay-quarantine-001", "APPROVAL_QUEUE_CONFLICT"),)


def test_approval_sync_rejects_request_id_path_escape_before_queue_path(tmp_path):
    result = sync_approval_receipts(
        foundry_root=tmp_path,
        source=FakeApprovalSource({}),
        requests={"../outside": SCOPE},
    )

    assert result.blocked == (("../outside", "INVALID_REQUEST_ID"),)
    assert not (tmp_path / "state/outside.json").exists()


def test_approval_sync_rejects_queue_not_bound_to_ledger(tmp_path):
    source = FakeApprovalSource({"relay-quarantine-001": receipt_document()})
    sync_approval_receipts(
        foundry_root=tmp_path,
        source=source,
        requests={"relay-quarantine-001": SCOPE},
    )
    ledger = tmp_path / "state/owner-approvals.json"
    ledger.unlink()

    result = sync_approval_receipts(
        foundry_root=tmp_path,
        source=source,
        requests={"relay-quarantine-001": SCOPE},
    )

    assert result.blocked == (("relay-quarantine-001", "APPROVAL_QUEUE_CONFLICT"),)
