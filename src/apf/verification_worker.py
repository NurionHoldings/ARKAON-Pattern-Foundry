"""Consume ledger-bound verification jobs with a real, isolated command executor.

This is a fixed-test automation worker, not an autonomous code author or auditor.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from uuid import NAMESPACE_URL, uuid4, uuid5

from .development_orchestrator import (
    DevelopmentOrchestrator,
    TaskContract,
    TaskKind,
    TaskResult,
    TaskStatus,
    Worker,
)
from .self_improvement_execution import (
    ApprovalExecutionError,
    parse_approval_receipt,
    sync_approval_receipts,
)
from .worker_runtime import ArkaonWorkerRuntime, MemoryReceiptSink, WorkerExecution

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
OPERATIONS = ["READ_WORKTREE", "RUN_TESTS", "GENERATE_ARTIFACT"]
ISOLATION_PROBE = """import os,json,socket,sys,subprocess
status=open('/proc/self/status').read()
assert 'NoNewPrivs:\t1' in status
assert 'CapEff:\t0000000000000000' in status
assert os.statvfs('/work').f_flag & os.ST_RDONLY
assert not any(k in os.environ for k in ('GITHUB_TOKEN','APF_CONSOLE_SESSION_SECRET','APF_WORKER_HOST_MARKER'))
s=socket.socket();s.settimeout(1)
try:
 s.connect(('192.0.2.1',80))
except OSError:
 pass
else:
 raise AssertionError('Network reachable')
finally:
 s.close()
print(json.dumps({'network_unreachable':True,'worktree_read_only':True,'capabilities_dropped':True,'no_new_privileges':True,'host_credentials_absent':True,'python':sys.version.split()[0],'node':subprocess.check_output(['node','--version'],text=True).strip()}))
"""
PROFILES = {
    "isolation": ("python", "-c", ISOLATION_PROBE),
    "learning": ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "tests/test_fundamental_learning_gates.py",
                 "tests/test_fundamental_learning_evidence.py",
                 "tests/test_learning_feedback_isolation.py"),
    "brand": ("node", "--test", "tests/brand-studio.test.cjs",
              "tests/brand-contrast-copy.test.cjs"),
    "platform": ("node", "--test", "tests/studio.test.cjs", "tests/platform-presets.test.cjs"),
}


class WorkerBlocked(ValueError):
    pass


class NotVerificationJob(WorkerBlocked):
    pass


def digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise WorkerBlocked("SYMLINK_INPUT")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorkerBlocked("OBJECT_REQUIRED")
    return value


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(("git", "-C", str(root), *args), capture_output=True,
                            text=True, encoding="utf-8", check=False, timeout=30)
    if result.returncode:
        raise WorkerBlocked("GIT_SOURCE_UNAVAILABLE")
    return result.stdout.strip()


def _git_json(root: Path, revision: str, path: str) -> dict:
    if not SHA.fullmatch(revision):
        raise WorkerBlocked("SOURCE_SHA_INVALID")
    result = json.loads(_git(root, "show", f"{revision}:{path}"))
    if not isinstance(result, dict):
        raise WorkerBlocked("SOURCE_OBJECT_REQUIRED")
    return result


def parse_plan(document: dict) -> dict:
    allowed = {"schema_version", "request_id", "kind", "base_sha", "candidate_sha",
               "profiles", "profile_digests", "allowed_paths", "allowed_operations", "timeout_seconds",
               "scope_digest", "merge_allowed", "deployment_allowed"}
    if set(document) != allowed or document.get("schema_version") != "apf.verification-plan/v1":
        raise WorkerBlocked("PLAN_SCHEMA_INVALID")
    if not isinstance(document.get("request_id"), str) or not ID.fullmatch(document["request_id"]):
        raise WorkerBlocked("REQUEST_ID_INVALID")
    if document.get("kind") != "VERIFY":
        raise WorkerBlocked("VERIFICATION_ONLY")
    for key in ("base_sha", "candidate_sha"):
        if not isinstance(document.get(key), str) or not SHA.fullmatch(document[key]):
            raise WorkerBlocked("FULL_COMMIT_SHA_REQUIRED")
    profiles = document.get("profiles")
    if (not isinstance(profiles, list) or not profiles
            or any(not isinstance(p, str) or p not in PROFILES for p in profiles)
            or len(set(profiles)) != len(profiles)):
        raise WorkerBlocked("PROFILE_NOT_ALLOWLISTED")
    if document.get("profile_digests") != {p: digest(list(PROFILES[p])) for p in profiles}:
        raise WorkerBlocked("PROFILE_COMMAND_DIGEST_MISMATCH")
    paths = document.get("allowed_paths")
    if not isinstance(paths, list) or not paths:
        raise WorkerBlocked("PATHS_REQUIRED")
    for path in paths:
        if (not isinstance(path, str) or not path or "\\" in path or ":" in path
                or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
                or path == "." or any(part.startswith(".") and part != ".github"
                                       for part in PurePosixPath(path).parts)):
            raise WorkerBlocked("UNSAFE_PATH")
    if document.get("allowed_operations") != OPERATIONS:
        raise WorkerBlocked("VERIFICATION_OPERATIONS_REQUIRED")
    if (type(document.get("timeout_seconds")) is not int
            or not 1 <= document["timeout_seconds"] <= 600):
        raise WorkerBlocked("TIMEOUT_INVALID")
    if document.get("merge_allowed") is not False or document.get("deployment_allowed") is not False:
        raise WorkerBlocked("AUTHORITY_ESCALATION")
    body = {key: value for key, value in document.items() if key != "scope_digest"}
    if document.get("scope_digest") != digest(body):
        raise WorkerBlocked("PLAN_DIGEST_MISMATCH")
    return document


def seed_approved_request(root: Path, repository: Path, request_id: str, source_sha: str) -> None:
    """Explicit intake of an immutable approved Git request; no arbitrary shell command."""
    if not ID.fullmatch(request_id):
        raise WorkerBlocked("REQUEST_ID_INVALID")
    plan = parse_plan(_git_json(repository, source_sha,
                               f"requests/verification/{request_id}.json"))
    approval = _git_json(repository, source_sha, f"approvals/self-improvement/{request_id}.json")
    if plan["request_id"] != request_id:
        raise WorkerBlocked("PLAN_REQUEST_MISMATCH")

    class Source:
        def fetch(self, requested):
            if requested != request_id:
                raise WorkerBlocked("REQUEST_MISMATCH")
            return approval, source_sha

    result = sync_approval_receipts(foundry_root=root, source=Source(),
                                    requests={request_id: plan["scope_digest"]})
    if result.blocked or result.pending:
        raise WorkerBlocked("APPROVAL_INTAKE_BLOCKED")


def _bound_plan(root: Path, repository: Path, queue_path: Path) -> tuple[dict, dict]:
    queue = _read(queue_path)
    request_id = queue.get("request_id")
    if (not isinstance(request_id, str) or not ID.fullmatch(request_id)
            or request_id != queue_path.stem
            or queue.get("schema_version") != "apf.approved-execution-job/1.0"
            or queue.get("state") != "OWNER_APPROVED"):
        raise WorkerBlocked("QUEUE_INVALID")
    ledger = _read(root / "state" / "owner-approvals.json")
    if ledger.get("schema_version") != "apf.owner-approval-ledger/1.0":
        raise WorkerBlocked("LEDGER_SCHEMA_INVALID")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise WorkerBlocked("LEDGER_ENTRIES_INVALID")
    matches = [e for e in entries if isinstance(e, dict) and e.get("request_id") == request_id]
    if len(matches) != 1:
        raise WorkerBlocked("UNIQUE_APPROVAL_REQUIRED")
    entry = matches[0]
    receipt = parse_approval_receipt(
        {**entry, "schema_version": "apf.owner-approval-receipt/1.0", "state": "OWNER_APPROVED"},
        source_commit_sha=entry.get("source_commit_sha", ""),
    )
    if any(queue.get(k) != entry.get(k) for k in
           ("scope_digest", "receipt_digest", "source_commit_sha")) or entry.get("receipt_digest") != receipt.digest():
        raise WorkerBlocked("LEDGER_BINDING_MISMATCH")
    if not _git(repository, "ls-tree", "--name-only", receipt.source_commit_sha, "--",
                f"requests/verification/{request_id}.json"):
        raise NotVerificationJob("NO_VERIFICATION_PLAN")
    plan = parse_plan(_git_json(repository, receipt.source_commit_sha,
                               f"requests/verification/{request_id}.json"))
    original = parse_approval_receipt(
        _git_json(repository, receipt.source_commit_sha,
                  f"approvals/self-improvement/{request_id}.json"),
        source_commit_sha=receipt.source_commit_sha,
    )
    if (original != receipt or plan["request_id"] != request_id
            or receipt.scope_digest != plan["scope_digest"]
            or list(receipt.allowed_paths) != plan["allowed_paths"]
            or list(receipt.allowed_operations) != plan["allowed_operations"]):
        raise WorkerBlocked("IMMUTABLE_APPROVAL_MISMATCH")
    changed = _git(repository, "diff", "--name-only", "--no-renames",
                   plan["base_sha"], plan["candidate_sha"]).splitlines()
    for name in changed:
        if not any(name == p or name.startswith(p + "/") for p in plan["allowed_paths"]):
            raise WorkerBlocked("CANDIDATE_OUTSIDE_SCOPE")
    for profile in plan["profiles"]:
        for name in PROFILES[profile]:
            if name.startswith("tests/"):
                _git(repository, "cat-file", "-e", f"{plan['candidate_sha']}:{name}")
                if not any(name == p or name.startswith(p + "/") for p in plan["allowed_paths"]):
                    raise WorkerBlocked("TEST_OUTSIDE_SCOPE")
    return plan, queue


class DockerVerificationExecutor:
    def __init__(self, worktree: Path, run_dir: Path, image: str, plan: dict):
        if not IMAGE.fullmatch(image):
            raise WorkerBlocked("PINNED_IMAGE_ID_REQUIRED")
        if "," in str(worktree):
            raise WorkerBlocked("UNSUPPORTED_MOUNT_PATH")
        self.worktree, self.run_dir, self.image, self.plan = worktree, run_dir, image, plan
        self.results: list[dict] = []

    def execute(self, task, *, sandbox_policy, attestation) -> WorkerExecution:
        if task.kind is not TaskKind.VERIFY or task.intent_fingerprint != self.plan["scope_digest"]:
            raise WorkerBlocked("EXECUTOR_CONTRACT_MISMATCH")
        if not shutil.which("docker"):
            raise WorkerBlocked("DOCKER_NOT_AVAILABLE")
        inspected = subprocess.run(("docker", "image", "inspect", self.image),
                                   capture_output=True, timeout=20, check=False)
        if inspected.returncode:
            raise WorkerBlocked("PINNED_IMAGE_NOT_AVAILABLE")
        for profile in self.plan["profiles"]:
            name = "apf-verify-" + uuid4().hex
            command = ["docker", "run", "--rm", "--pull=never", "--name", name,
                       "--network=none", "--read-only", "--cap-drop=ALL",
                       "--security-opt=no-new-privileges", "--pids-limit=128",
                       "--memory=1g", "--cpus=2", "--user=65534:65534",
                       "--tmpfs=/tmp:rw,noexec,nosuid,size=256m,mode=1777",
                       "--mount", f"type=bind,src={self.worktree},dst=/work,readonly",
                       "--workdir=/work", "--env=PYTHONPATH=/work/src",
                       "--env=PYTHONDONTWRITEBYTECODE=1", "--env=HOME=/tmp",
                       self.image, *PROFILES[profile]]
            log = self.run_dir / f"{profile}.log"
            started = time.monotonic()
            returncode, reason = -1, None
            with log.open("wb") as stream:
                process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
                try:
                    while process.poll() is None:
                        if time.monotonic() - started > self.plan["timeout_seconds"]:
                            reason = "TIMEOUT"
                            break
                        if log.stat().st_size > 4 * 1024 * 1024:
                            reason = "OUTPUT_LIMIT"
                            break
                        time.sleep(0.05)
                    if reason:
                        process.kill()
                    returncode = process.wait(timeout=10)
                finally:
                    subprocess.run(("docker", "rm", "-f", name), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=20, check=False)
            if log.stat().st_size > 4 * 1024 * 1024:
                with log.open("r+b") as stream:
                    stream.truncate(4 * 1024 * 1024)
                reason = "OUTPUT_LIMIT"
            result = {"profile": profile, "command": list(PROFILES[profile]),
                      "returncode": returncode, "reason": reason,
                      "log_sha256": sha256(log.read_bytes()).hexdigest(),
                      "isolation": {"network": "none", "read_only": True,
                                    "cap_drop": "ALL", "no_new_privileges": True}}
            self.results.append(result)
        passed = all(r["returncode"] == 0 and not r["reason"] for r in self.results)
        _write(self.run_dir / "profile-results.json", self.results)
        return WorkerExecution(TaskResult(("profile-results.json",),
                               tuple(f"{r['profile']}:{r['returncode']}" for r in self.results),
                               "PASS" if passed else "FAIL"), ())


def process_verification_queue(*, foundry_root: Path, repository_root: Path, image: str,
                               worker_id: str = "arkaon-verification-worker", max_jobs: int = 3,
                               executor_factory=DockerVerificationExecutor) -> dict:
    root, repository = foundry_root.resolve(), repository_root.resolve()
    if not IMAGE.fullmatch(image):
        raise WorkerBlocked("PINNED_IMAGE_ID_REQUIRED")
    if not ID.fullmatch(worker_id) or type(max_jobs) is not int or not 1 <= max_jobs <= 30:
        raise WorkerBlocked("WORKER_CONFIG_INVALID")
    state = root / "state" / "verification-worker"
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "worker.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise WorkerBlocked("WORKER_ALREADY_RUNNING") from exc
    summary = {"schema_version": "apf.verification-worker-cycle/v1", "worker_id": worker_id,
               "passed": [], "failed": [], "blocked": [], "already_completed": [], "skipped": [],
               "merge_allowed": False, "deployment_allowed": False}
    try:
        os.write(descriptor, str(os.getpid()).encode())
        paths = sorted((root / "state" / "self-improvement-execution-queue").glob("*.json"))
        handled = 0
        for queue_path in paths:
            if handled >= max_jobs:
                break
            try:
                plan, queue = _bound_plan(root, repository, queue_path)
                handled += 1
                done_path = state / "completed" / f"{plan['request_id']}.json"
                if done_path.exists():
                    done = _read(done_path)
                    recorded = done.get("evidence_digest")
                    if (recorded != digest({k: v for k, v in done.items() if k != "evidence_digest"})
                            or done.get("binding_digest") != digest({"plan": plan, "queue": queue})):
                        raise WorkerBlocked("COMPLETED_JOB_CONFLICT")
                    summary["already_completed"].append(plan["request_id"])
                    continue
                execution_id = uuid4().hex
                claim_path = state / "claims" / f"{plan['request_id']}.json"
                claim_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    claim_fd = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError as exc:
                    raise WorkerBlocked("INCOMPLETE_EXECUTION_REQUIRES_REVIEW") from exc
                with os.fdopen(claim_fd, "w", encoding="utf-8") as stream:
                    json.dump({"execution_id": execution_id, "worker_id": worker_id,
                               "binding_digest": digest({"plan": plan, "queue": queue})}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                run_dir = state / "runs" / execution_id
                run_dir.mkdir(parents=True)
                worktree = state / "worktrees" / execution_id
                worktree.parent.mkdir(parents=True, exist_ok=True)
                _git(repository, "worktree", "add", "--detach", str(worktree), plan["candidate_sha"])
                if _git(worktree, "rev-parse", "HEAD") != plan["candidate_sha"] or _git(worktree, "status", "--porcelain"):
                    raise WorkerBlocked("CLEAN_CHECKOUT_REQUIRED")
                ack = {"schema_version": "apf.verification-worker-receipt/v1",
                       "request_id": plan["request_id"], "worker_id": worker_id,
                       "execution_id": execution_id, "tested_head": plan["candidate_sha"],
                       "base_sha": plan["base_sha"], "approval_source_sha": queue["source_commit_sha"],
                       "receipt_digest": queue["receipt_digest"], "scope_digest": plan["scope_digest"],
                       "binding_digest": digest({"plan": plan, "queue": queue}),
                       "started_at": datetime.now(UTC).isoformat(), "status": "RUNNING",
                       "worker_kind": "FIXED_TEST_AUTOMATION", "container_image_id": image,
                       "executor_source_sha": _git(repository, "rev-parse", "HEAD"),
                       "host_platform": sys.platform,
                       "first_verification_complete": False, "independent_audit_status": "NOT_RUN",
                       "improvement_accepted": False, "merge_allowed": False, "deployment_allowed": False}
                _write(run_dir / "ack.json", ack)
                orchestrator = DevelopmentOrchestrator()
                task = TaskContract(uuid5(NAMESPACE_URL, plan["scope_digest"]), TaskKind.VERIFY,
                                    plan["scope_digest"], "Run approved fixed verification profiles",
                                    tuple(plan["allowed_paths"]), ("profile-results.json",),
                                    requested_operations=tuple(OPERATIONS), approval_ref=queue["receipt_digest"])
                orchestrator.submit(task)
                executor = executor_factory(worktree, run_dir, image, plan)
                runtime = ArkaonWorkerRuntime(orchestrator,
                          Worker(worker_id, frozenset({TaskKind.VERIFY})), executor,
                          MemoryReceiptSink(), worktree_root=worktree)
                receipt = runtime.run_once()
                passed = receipt is not None and receipt.status is TaskStatus.SUCCEEDED
                if _git(worktree, "status", "--porcelain"):
                    passed = False
                result = {**ack, "status": "PASS" if passed else "FAIL",
                          "finished_at": datetime.now(UTC).isoformat(),
                          "runtime_receipt": asdict(receipt) if receipt else None,
                          "profiles": getattr(executor, "results", [])}
                # UUID and enum values in the runtime receipt are serialized explicitly.
                if result["runtime_receipt"]:
                    result["runtime_receipt"]["task_id"] = str(receipt.task_id)
                    result["runtime_receipt"]["status"] = receipt.status.value
                profile_results = run_dir / "profile-results.json"
                result["profile_results_sha256"] = (
                    sha256(profile_results.read_bytes()).hexdigest() if profile_results.is_file() else None
                )
                result["evidence_digest"] = digest(result)
                _write(run_dir / "result.json", result)
                _write(done_path, result)
                summary["passed" if passed else "failed"].append(plan["request_id"])
            except NotVerificationJob:
                summary["skipped"].append(queue_path.stem)
            except (WorkerBlocked, ApprovalExecutionError, OSError, ValueError, TypeError,
                    KeyError, subprocess.SubprocessError) as exc:
                summary["blocked"].append({"request_id": queue_path.stem,
                                           "reason": str(exc) if isinstance(exc, WorkerBlocked)
                                           else type(exc).__name__})
        _write(state / "latest.json", summary)
        return summary
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)


def start_verification_worker(*, foundry_root: Path, repository_root: Path, image: str,
                              request_id: str | None = None) -> bool:
    if not IMAGE.fullmatch(image):
        raise WorkerBlocked("PINNED_IMAGE_ID_REQUIRED")
    state = foundry_root.resolve() / "state" / "verification-worker"
    if (state / "worker.lock").exists():
        return False
    state.mkdir(parents=True, exist_ok=True)
    intake = ()
    if request_id:
        if not ID.fullmatch(request_id):
            raise WorkerBlocked("REQUEST_ID_INVALID")
        source_sha = _git(repository_root, "log", "-1", "--format=%H", "--",
                          f"approvals/self-improvement/{request_id}.json")
        if not SHA.fullmatch(source_sha):
            raise WorkerBlocked("APPROVAL_SOURCE_NOT_AVAILABLE")
        intake = ("--seed-request", request_id, "--approval-source-sha", source_sha)
    with (state / "launcher.log").open("ab") as log:
        subprocess.Popen((sys.executable, "-m", "apf.verification_worker",
                          "--foundry-root", str(foundry_root.resolve()),
                          "--repository-root", str(repository_root.resolve()), "--image", image, *intake),
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         env={**os.environ, "PYTHONPATH": str(repository_root.resolve() / "src")})
    return True



def load_verification_connection(foundry_root: Path) -> tuple[str | None, str | None]:
    path = foundry_root / "state" / "verification-worker-connection.json"
    if not path.exists():
        return None, None
    value = _read(path)
    if (set(value) != {"schema_version", "image_id", "request_id"}
            or value.get("schema_version") != "apf.verification-worker-connection/v1"
            or not isinstance(value.get("image_id"), str) or not IMAGE.fullmatch(value["image_id"])
            or not isinstance(value.get("request_id"), str) or not ID.fullmatch(value["request_id"])):
        raise WorkerBlocked("CONNECTION_CONFIG_INVALID")
    return value["image_id"], value["request_id"]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--worker-id", default="arkaon-verification-worker")
    parser.add_argument("--seed-request")
    parser.add_argument("--approval-source-sha")
    args = parser.parse_args()
    expected_module = args.repository_root.resolve() / "src" / "apf" / "verification_worker.py"
    if Path(__file__).resolve() != expected_module:
        raise WorkerBlocked("EXECUTOR_SOURCE_LOCATION_MISMATCH")
    if _git(args.repository_root, "status", "--porcelain", "--untracked-files=no", "--", "src/apf"):
        raise WorkerBlocked("EXECUTOR_SOURCE_DIRTY")
    if args.seed_request:
        if not args.approval_source_sha:
            parser.error("--approval-source-sha required for explicit intake")
        seed_approved_request(args.foundry_root, args.repository_root,
                              args.seed_request, args.approval_source_sha)
    result = process_verification_queue(foundry_root=args.foundry_root,
                repository_root=args.repository_root, image=args.image, worker_id=args.worker_id)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["blocked"] or result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
