"""Queue/ledger/commit/lease tests. Docker execution is additionally exercised in CI."""
import json
import subprocess
from typing import ClassVar

import pytest

from apf import verification_worker as worker
from apf.development_orchestrator import TaskResult
from apf.worker_runtime import WorkerExecution

IMAGE = "sha256:" + "a" * 64


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def job(tmp_path):
    repo, state = tmp_path / "repo", tmp_path / "runtime"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    for command in worker.PROFILES.values():
        for arg in command:
            if arg.startswith("tests/"):
                p = repo / arg
                p.parent.mkdir(exist_ok=True)
                p.write_text("# fixture\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src/example.py").write_text("value=1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "baseline")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "src/example.py").write_text("value=2\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "candidate")
    candidate = git(repo, "rev-parse", "HEAD")
    plan = {"schema_version": "apf.verification-plan/v1", "request_id": "verify-fixture",
            "kind": "VERIFY", "base_sha": base, "candidate_sha": candidate,
            "profiles": ["isolation", "learning"], "allowed_paths": ["src", "tests"],
            "allowed_operations": worker.OPERATIONS, "timeout_seconds": 60,
            "merge_allowed": False, "deployment_allowed": False}
    plan["profile_digests"] = {p: worker.digest(list(worker.PROFILES[p])) for p in plan["profiles"]}
    plan["scope_digest"] = worker.digest(plan)
    approval = {"schema_version": "apf.owner-approval-receipt/1.0", "state": "OWNER_APPROVED",
                "request_id": plan["request_id"], "scope_digest": plan["scope_digest"],
                "approver": "TEST FIXTURE ONLY", "approved_at": "2026-11-05T00:00:00+00:00",
                "allowed_paths": plan["allowed_paths"], "allowed_operations": worker.OPERATIONS}
    write(repo / "requests/verification/verify-fixture.json", plan)
    write(repo / "approvals/self-improvement/verify-fixture.json", approval)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture approval")
    source = git(repo, "rev-parse", "HEAD")
    worker.seed_approved_request(state, repo, plan["request_id"], source)
    return repo, state, plan, source


class TestExecutor:
    __test__ = False
    calls: ClassVar[list] = []

    def __init__(self, worktree, run_dir, image, plan):
        self.run_dir = run_dir
        self.plan = plan
        self.results = []

    def execute(self, task, **kwargs):
        self.calls.append(task)
        from hashlib import sha256
        log = b"TEST DOUBLE ONLY, NOT AN EXECUTION RESULT\n"
        self.results = []
        for profile in self.plan["profiles"]:
            (self.run_dir / f"{profile}.log").write_bytes(log)
            self.results.append({"profile": profile, "returncode": 0, "reason": None,
                                 "fixture_only": True, "log_sha256": sha256(log).hexdigest()})
        write(self.run_dir / "profile-results.json", self.results)
        return WorkerExecution(TaskResult(("profile-results.json",), ("FIXTURE_ONLY",), "PASS"), ())


def run(job, **kwargs):
    repo, state, _, _ = job
    TestExecutor.calls = []
    return worker.process_verification_queue(foundry_root=state, repository_root=repo,
               image=IMAGE, worker_id="TEST-DOUBLE-NOT-REAL-ARKAON", executor_factory=TestExecutor, **kwargs)


def test_claim_execute_receipt_and_idempotence(job):
    result = run(job)
    assert result["passed"] == ["verify-fixture"]
    assert len(TestExecutor.calls) == 1
    repo, root, plan, source = job
    done = worker._read(root / "state/verification-worker/completed/verify-fixture.json")
    assert done["tested_head"] == plan["candidate_sha"]
    assert done["approval_source_sha"] == source
    assert done["runtime_receipt"]["worker_id"] == "TEST-DOUBLE-NOT-REAL-ARKAON"
    assert done["first_verification_complete"] is False
    assert done["independent_audit_status"] == "NOT_RUN"
    assert done["merge_allowed"] is done["deployment_allowed"] is False
    assert done["evidence_digest"] == worker.digest({k: v for k, v in done.items() if k != "evidence_digest"})
    assert run(job)["already_completed"] == ["verify-fixture"]
    assert not TestExecutor.calls
    assert git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("field,value", [
    ("scope_digest", "b" * 64), ("receipt_digest", "b" * 64),
    ("source_commit_sha", "b" * 40), ("request_id", "../escape"),
])
def test_tampered_queue_never_executes(job, field, value):
    path = job[1] / "state/self-improvement-execution-queue/verify-fixture.json"
    queue = worker._read(path)
    queue[field] = value
    write(path, queue)
    assert run(job)["blocked"]
    assert not TestExecutor.calls


def test_corrupt_packet_does_not_block_later_job(job):
    bad = job[1] / "state/self-improvement-execution-queue/00-bad.json"
    bad.write_bytes(b"\xff")
    result = run(job, max_jobs=1)
    assert result["blocked"] and result["passed"] == ["verify-fixture"]
    assert bad.read_bytes() == b"\xff"


def test_ledger_edit_even_with_recomputed_checksum_cannot_override_git_approval(job):
    root = job[1]
    path = root / "state/owner-approvals.json"
    ledger = worker._read(path)
    entry = ledger["entries"][0]
    entry["approver"] = "forged approver"
    receipt = worker.parse_approval_receipt({**entry, "schema_version": "apf.owner-approval-receipt/1.0",
                                          "state": "OWNER_APPROVED"}, source_commit_sha=entry["source_commit_sha"])
    entry["receipt_digest"] = receipt.digest()
    write(path, ledger)
    queue_path = root / "state/self-improvement-execution-queue/verify-fixture.json"
    queue = worker._read(queue_path)
    queue["receipt_digest"] = receipt.digest()
    write(queue_path, queue)
    result = run(job)
    assert result["blocked"][0]["reason"] == "IMMUTABLE_APPROVAL_MISMATCH"
    assert not TestExecutor.calls


def test_incomplete_claim_is_held_not_replayed(job):
    path = job[1] / "state/verification-worker/claims/verify-fixture.json"
    write(path, {"execution_id": "interrupted"})
    result = run(job)
    assert result["blocked"][0]["reason"] == "INCOMPLETE_EXECUTION_REQUIRES_REVIEW"
    assert not TestExecutor.calls


def test_tampered_completed_receipt_does_not_grant_pass(job):
    run(job)
    path = job[1] / "state/verification-worker/completed/verify-fixture.json"
    done = worker._read(path)
    done["status"] = "FORGED"
    write(path, done)
    assert run(job)["blocked"][0]["reason"] == "COMPLETED_JOB_CONFLICT"
    assert not TestExecutor.calls


def test_local_plan_edit_cannot_change_immutable_job(job):
    repo, _, _, _ = job
    write(repo / "requests/verification/verify-fixture.json", {"profiles": ["arbitrary command"]})
    assert run(job)["passed"]
    assert TestExecutor.calls[0].kind.value == "VERIFY"


@pytest.mark.parametrize("changes", [
    {"profiles": ["node --eval process.exit(0)"]}, {"kind": "BUILD"},
    {"allowed_paths": ["../secrets"]}, {"allowed_paths": ["C:/secrets"]},
    {"allowed_paths": [".git"]}, {"timeout_seconds": True}, {"timeout_seconds": 601},
    {"merge_allowed": True}, {"deployment_allowed": True},
    {"allowed_operations": ["READ_SECRET_VALUE"]}, {"candidate_sha": "main"},
    {"command": ["arbitrary"]},
])
def test_plan_rejects_unapproved_capabilities(job, changes):
    plan = {**job[2], **changes}
    with pytest.raises(worker.WorkerBlocked):
        worker.parse_plan(plan)


def test_worker_lock_prevents_concurrent_consumption(job):
    lock = job[1] / "state/verification-worker/worker.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("interrupted owner", encoding="utf-8")
    with pytest.raises(worker.WorkerBlocked, match="WORKER_ALREADY_RUNNING"):
        run(job)
    assert lock.read_text() == "interrupted owner"


def test_image_must_be_local_content_id(job):
    with pytest.raises(worker.WorkerBlocked, match="PINNED_IMAGE_ID_REQUIRED"):
        worker.process_verification_queue(foundry_root=job[1], repository_root=job[0], image="latest")


def test_async_launcher_uses_fixed_python_module_and_no_shell(job, monkeypatch):
    seen = []
    monkeypatch.setattr(worker, "_git", lambda *args: job[3])
    monkeypatch.setattr(worker.subprocess, "Popen", lambda command, **kw: seen.append((command, kw)))
    assert worker.start_verification_worker(foundry_root=job[1], repository_root=job[0],
                                            image=IMAGE, request_id="verify-fixture")
    command, kwargs = seen[0]
    assert command[1:3] == ("-m", "apf.verification_worker")
    assert "--seed-request" in command and job[3] in command
    assert "shell" not in kwargs


def test_docker_executor_uses_read_only_networkless_unprivileged_container(job, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(worker.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))

    class Process:
        def __init__(self, command, **kwargs):
            seen.append((command, kwargs))
        def poll(self):
            return 0
        def wait(self, **kwargs):
            return 0

    monkeypatch.setattr(worker.subprocess, "Popen", Process)
    plan = job[2]
    executor = worker.DockerVerificationExecutor(job[0], tmp_path, IMAGE, plan)
    from uuid import uuid4

    from apf.development_orchestrator import TaskContract, TaskKind
    task = TaskContract(uuid4(), TaskKind.VERIFY, plan["scope_digest"], "fixture", ("tests",), ())
    result = executor.execute(task, sandbox_policy=None, attestation=None)
    assert result.result.outcome == "PASS"
    command, kwargs = seen[0]
    for flag in ["--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534", "--pull=never"]:
        assert flag in command
    assert any("dst=/work,readonly" in arg for arg in command)
    assert "--privileged" not in command
    assert not any("docker.sock" in arg for arg in command)
    assert "env" not in kwargs and "shell" not in kwargs


def test_relay_can_launch_worker_without_blocking_mailbox(tmp_path, monkeypatch):
    from test_self_improvement_relay import FakePublisher

    import apf.self_improvement_relay as relay
    calls = []
    monkeypatch.setattr(relay, "start_verification_worker", lambda **kw: calls.append(kw) or True)
    result = relay.relay_cycle(foundry_root=tmp_path, publisher=FakePublisher(),
                              verification_image=IMAGE, verification_request="verify-fixture")
    assert result.verification_worker_launched is True
    assert calls[0]["request_id"] == "verify-fixture"
    assert result.mailbox


def test_connection_configuration_is_explicit_and_fails_closed(tmp_path):
    assert worker.load_verification_connection(tmp_path) == (None, None)
    path = tmp_path / 'state/verification-worker-connection.json'
    write(path, {'schema_version': 'apf.verification-worker-connection/v1',
                 'image_id': IMAGE, 'request_id': 'verify-fixture'})
    assert worker.load_verification_connection(tmp_path) == (IMAGE, 'verify-fixture')
    value = worker._read(path)
    value['command'] = ['anything']
    write(path, value)
    with pytest.raises(worker.WorkerBlocked):
        worker.load_verification_connection(tmp_path)


def test_docker_unavailable_never_falls_back_to_host_execution(job, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.shutil, 'which', lambda name: None)
    executor = worker.DockerVerificationExecutor(job[0], tmp_path, IMAGE, job[2])
    from uuid import uuid4

    from apf.development_orchestrator import TaskContract, TaskKind
    task = TaskContract(uuid4(), TaskKind.VERIFY, job[2]['scope_digest'], 'fixture', ('tests',), ())
    with pytest.raises(worker.WorkerBlocked, match='DOCKER_NOT_AVAILABLE'):
        executor.execute(task, sandbox_policy=None, attestation=None)


def test_legacy_queue_does_not_starve_verification_job(job):
    repo, root, _, _ = job
    approval = {'schema_version': 'apf.owner-approval-receipt/1.0', 'state': 'OWNER_APPROVED',
                'request_id': '00-legacy', 'scope_digest': 'c' * 64, 'approver': 'FIXTURE',
                'approved_at': '2026-11-05T00:00:00+00:00', 'allowed_paths': ['tests'],
                'allowed_operations': worker.OPERATIONS}
    write(repo / 'approvals/self-improvement/00-legacy.json', approval)
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'legacy fixture')
    source = git(repo, 'rev-parse', 'HEAD')

    class Source:
        def fetch(self, request_id):
            return approval, source

    worker.sync_approval_receipts(foundry_root=root, source=Source(), requests={'00-legacy': 'c' * 64})
    result = run(job, max_jobs=1)
    assert result['skipped'] == ['00-legacy']
    assert result['passed'] == ['verify-fixture']


def test_unavailable_executor_records_failure_and_does_not_retry(job, monkeypatch):
    monkeypatch.setattr(worker.shutil, 'which', lambda name: None)
    repo, root, _, _ = job
    result = worker.process_verification_queue(foundry_root=root, repository_root=repo, image=IMAGE)
    assert result['failed'] == ['verify-fixture']
    again = worker.process_verification_queue(foundry_root=root, repository_root=repo, image=IMAGE)
    assert again['already_completed'] == ['verify-fixture']
    assert not again['passed']
    assert again['failed'] == ['verify-fixture']


def test_candidate_diff_outside_approved_paths_is_blocked(job, tmp_path):
    repo, _, plan, _ = job
    plan = {**plan, 'allowed_paths': ['tests']}
    plan['scope_digest'] = worker.digest({k: v for k, v in plan.items() if k != 'scope_digest'})
    approval_path = repo / 'approvals/self-improvement/verify-fixture.json'
    approval = worker._read(approval_path)
    approval.update(scope_digest=plan['scope_digest'], allowed_paths=plan['allowed_paths'])
    write(approval_path, approval)
    write(repo / 'requests/verification/verify-fixture.json', plan)
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'narrower fixture approval')
    source = git(repo, 'rev-parse', 'HEAD')
    root = tmp_path / 'separate-runtime'
    worker.seed_approved_request(root, repo, 'verify-fixture', source)
    result = worker.process_verification_queue(foundry_root=root, repository_root=repo,
                                              image=IMAGE, executor_factory=TestExecutor)
    assert result['blocked'][0]['reason'] == 'CANDIDATE_OUTSIDE_SCOPE'


def test_image_build_does_not_copy_pc_runtime_or_secrets():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root/'Dockerfile.verification-worker').read_text()
    assert 'COPY . .' not in dockerfile
    assert 'COPY src/apf' in dockerfile
    exclusions = (root/'Dockerfile.verification-worker.dockerignore').read_text().splitlines()
    assert exclusions[0] == '**'
    assert '!state/' not in exclusions
    assert '!private/' not in exclusions
    assert '!.env' not in exclusions


def test_profile_command_changes_invalidate_old_approval(job, monkeypatch):
    old_plan = job[2]
    monkeypatch.setitem(worker.PROFILES, 'learning', ('python', '-c', 'changed command'))
    with pytest.raises(worker.WorkerBlocked, match='PROFILE_COMMAND_DIGEST_MISMATCH'):
        worker.parse_plan(old_plan)


def test_operational_plan_covers_all_selected_candidate_paths():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    plan = worker.parse_plan(worker._read(root/'requests/verification/main-integration-20261105-verify-v2.json'))
    selection = worker._read(root/'docs/integration/main-20261105/source-selection.json')
    outside = [r['path'] for r in selection['files']
               if not any(r['path'] == p or r['path'].startswith(p+'/') for p in plan['allowed_paths'])]
    assert outside == []


def test_preflight_checks_scope_without_claiming_execution(job, monkeypatch, capsys):
    repo, state, _, source = job
    monkeypatch.setattr(worker, '__file__', str(repo/'src/apf/verification_worker.py'))
    monkeypatch.setattr(worker.sys, 'argv', ['worker', '--repository-root', str(repo),
                       '--foundry-root', str(state), '--seed-request', 'verify-fixture',
                       '--approval-source-sha', source, '--preflight'])
    assert worker.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'PASS' and result['execution_started'] is False
    assert not (state/'state/verification-worker/runs').exists()


def test_completed_log_corruption_blocks_reuse(job):
    run(job)
    result_path = job[1]/'state/verification-worker/completed/verify-fixture.json'
    done = worker._read(result_path)
    log = result_path.parent.parent/'runs'/done['execution_id']/'learning.log'
    log.write_bytes(b'corrupted bytes')
    assert run(job)['blocked'][0]['reason'] == 'COMPLETED_LOG_HASH_MISMATCH'
    assert not TestExecutor.calls


def test_completed_job_is_not_respawned_by_relay_launcher(job, monkeypatch):
    run(job)
    original = worker.subprocess.Popen
    def popen(command, **kwargs):
        if '-m' in command and 'apf.verification_worker' in command:
            pytest.fail('must not spawn completed task')
        return original(command, **kwargs)
    monkeypatch.setattr(worker.subprocess, 'Popen', popen)
    assert worker.start_verification_worker(foundry_root=job[1], repository_root=job[0],
                                           image=IMAGE, request_id='verify-fixture') is False
    status = worker._read(job[1]/'state/verification-worker/launcher-status.json')
    assert status['status'] == 'ALREADY_COMPLETED' and status['result_status'] == 'PASS'


def test_explicit_approval_source_change_conflicts_with_existing_ledger(job):
    repo, root, _, _ = job
    (repo/'note.txt').write_text('unrelated change')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'new head is not the approval change commit')
    with pytest.raises(worker.WorkerBlocked, match='APPROVAL_SOURCE_CONFLICT'):
        worker.seed_approved_request(root, repo, 'verify-fixture', git(repo, 'rev-parse', 'HEAD'))


def test_isolation_is_mandatory_before_candidate_tests(job):
    plan = {**job[2], 'profiles': ['learning']}
    with pytest.raises(worker.WorkerBlocked, match='ISOLATION_MUST_RUN_FIRST'):
        worker.parse_plan(plan)


@pytest.mark.parametrize('scenario,exit_code,expected', [
    ('probe_failure', 1, None), ('cleanup_failure', 0, 'CLEANUP_REQUIRED'),
    ('timeout', -9, 'TIMEOUT'),
])
def test_isolation_or_safety_failure_stops_later_profiles(job, tmp_path, monkeypatch,
                                                       scenario, exit_code, expected):
    calls = []
    monkeypatch.setattr(worker.shutil, 'which', lambda name: '/usr/bin/docker')
    def docker_run(command, **kwargs):
        if command[1] == 'rm' and scenario == 'cleanup_failure':
            return subprocess.CompletedProcess(command, 1, stderr='daemon unavailable')
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(worker.subprocess, 'run', docker_run)
    class Process:
        def __init__(self, command, **kwargs):
            calls.append(command)
        def poll(self):
            return None if scenario == 'timeout' else exit_code
        def kill(self):
            pass
        def wait(self, **kwargs):
            return exit_code
    monkeypatch.setattr(worker.subprocess, 'Popen', Process)
    if scenario == 'timeout':
        clock = iter([0, 1000])
        monkeypatch.setattr(worker.time, 'monotonic', lambda: next(clock))
    executor = worker.DockerVerificationExecutor(job[0], tmp_path, IMAGE, job[2])
    from uuid import uuid4

    from apf.development_orchestrator import TaskContract, TaskKind
    task = TaskContract(uuid4(), TaskKind.VERIFY, job[2]['scope_digest'], 'fixture', ('tests',), ())
    result = executor.execute(task, sandbox_policy=None, attestation=None)
    assert result.result.outcome == 'FAIL' and len(calls) == 1
    assert executor.results[0]['profile'] == 'isolation'
    assert executor.results[0]['reason'] == expected
    assert executor.not_run_profiles == ['learning']
    record = worker._read(tmp_path/'isolation-container.json')
    assert record['container_name'].startswith('apf-verify-')
    assert record['status'] == ('CLEANUP_REQUIRED' if scenario == 'cleanup_failure' else 'REMOVED')
