"""Central ARKAON orchestrator for explicitly registered platform workspaces.

Collects only public metadata digests from platform trees. Never copies member,
order, location, settlement, contract, or identity data into Foundry knowledge.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from .experience_audit_bridge import run_platform_experience_audit
from .experience_operations_audit import AuditRejected, ImprovementProposal

SCHEMA_PLATFORMS = "apf.central-platforms/v1"
SCHEMA_WORKSPACE = "arkaon.workspace/v1"
_FORBIDDEN_NAME = re.compile(
    r"(^|/)(\.env|secrets?|credentials?|tokens?|certs?|certificates?|pii|personal_data|"
    r"node_modules/|__pycache__/|\.git/)(/|$|\.)",
    re.IGNORECASE,
)
_FORBIDDEN_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".mdb"})
_FORBIDDEN_KNOWLEDGE_KEYS = frozenset(
    {
        "member",
        "order",
        "location",
        "settlement",
        "contract_body",
        "identity",
        "pii",
        "credential",
        "secret",
    }
)


class OrchestratorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _normalize_platform_path(path: Path, *, foundry_root: Path) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError as exc:
        raise OrchestratorError("PLATFORM_PATH_INVALID", f"cannot resolve platform path: {path}") from exc
    if not resolved.is_absolute():
        raise OrchestratorError("PLATFORM_PATH_RELATIVE", "platform path must be absolute after normalization")
    try:
        resolved.relative_to(foundry_root.resolve())
    except ValueError:
        return resolved
    raise OrchestratorError("PLATFORM_INSIDE_FOUNDRY", "platform workspace must stay outside foundry root")


def _resolve_analysis_root(platform_path: Path, root_name: str) -> Path:
    if root_name.startswith(("/", "\\")) or ".." in Path(root_name).parts:
        raise OrchestratorError("ANALYSIS_ROOT_ESCAPE", f"unsafe analysis root: {root_name}")
    candidate = (platform_path / root_name).resolve()
    try:
        candidate.relative_to(platform_path.resolve())
    except ValueError as exc:
        raise OrchestratorError("ANALYSIS_ROOT_ESCAPE", f"analysis root escapes platform: {root_name}") from exc
    return candidate


def _matches_forbidden(relative: str, forbidden_globs: tuple[str, ...]) -> bool:
    normalized = relative.replace("\\", "/")
    if _FORBIDDEN_NAME.search(normalized):
        return True
    if Path(normalized).suffix.lower() in _FORBIDDEN_SUFFIXES:
        return True
    for pattern in forbidden_globs:
        glob = pattern.replace("\\", "/")
        if fnmatch.fnmatch(normalized, glob) or fnmatch.fnmatch(Path(normalized).name, glob):
            return True
        bare = glob.removeprefix("**/")
        if any(fnmatch.fnmatch(part, bare) for part in normalized.split("/")):
            return True
    return False


def _iter_safe_files(platform_root: Path, root: Path) -> list[Path]:
    platform_resolved = platform_root.resolve()
    collected: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            entry_path = Path(entry.path)
            if entry.is_file(follow_symlinks=False):
                try:
                    entry_path.resolve().relative_to(platform_resolved)
                except ValueError:
                    continue
                collected.append(entry_path)
            elif entry.is_dir(follow_symlinks=False):
                try:
                    entry_path.resolve().relative_to(platform_resolved)
                except ValueError:
                    continue
                stack.append(entry_path)
    return sorted(collected)


def _read_candidate_commit(platform_path: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(platform_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = completed.stdout.strip()
    return commit or None


class RunLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self._fd, f"{datetime.now(UTC).isoformat()}\n".encode())
        except FileExistsError as exc:
            raise OrchestratorError("RUN_LOCK_HELD", "orchestrator already running") from exc

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self.path.unlink(missing_ok=True)


class InboxStage(str, Enum):
    RESEARCH = "research"
    ETHERNIAN_REVIEW = "eternian-review"
    SELF_IMPROVEMENT = "self-improvement"
    OPERATOR_DECISION = "operator-decision"


class PlatformStage(str, Enum):
    REGISTERED = "REGISTERED"
    STATUS_CHECKED = "STATUS_CHECKED"
    ANALYZED = "ANALYZED"
    GUIDE_UPDATED = "GUIDE_UPDATED"
    QUARANTINED = "QUARANTINED"
    ETERNIAN_PENDING = "ETERNIAN_PENDING"
    PROPOSED = "PROPOSED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PlatformRegistration:
    platform_id: str
    path: Path
    enabled: bool = True


@dataclass(frozen=True)
class PlatformWorkspace:
    platform_id: str
    foundry_root: Path
    allowed_analysis_roots: tuple[str, ...]
    forbidden_globs: tuple[str, ...]
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> PlatformWorkspace:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != SCHEMA_WORKSPACE:
            raise OrchestratorError("WORKSPACE_SCHEMA", "unsupported workspace schema")
        if document.get("production_change_allowed"):
            raise OrchestratorError("PRODUCTION_CHANGE_FORBIDDEN", "workspace cannot allow production changes")
        roots = tuple(document.get("allowed_analysis_roots") or ())
        if not roots:
            raise OrchestratorError("WORKSPACE_ROOTS_REQUIRED", "allowed analysis roots are required")
        return cls(
            platform_id=str(document["platform_id"]),
            foundry_root=Path(str(document["foundry_root"])),
            allowed_analysis_roots=roots,
            forbidden_globs=tuple(document.get("forbidden_globs") or (".env", "**/secrets/**")),
            production_change_allowed=False,
        )


@dataclass(frozen=True)
class SharedPolicy:
    automatic_learning: bool = False
    production_change_allowed: bool = False
    collect_platform_operational_data: bool = False
    knowledge_allowed_kinds: frozenset[str] = frozenset(
        {"public_reference", "policy", "schema", "synthetic_test_pattern", "generalized_dev_knowledge"}
    )

    @classmethod
    def load(cls, path: Path) -> SharedPolicy:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("automatic_learning") or document.get("production_change_allowed"):
            raise OrchestratorError("POLICY_FORBIDDEN", "central policy must remain propose-only")
        if document.get("collect_platform_operational_data"):
            raise OrchestratorError("OPERATIONAL_DATA_FORBIDDEN", "platform operational data stays isolated")
        return cls(
            automatic_learning=bool(document.get("automatic_learning")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            collect_platform_operational_data=bool(document.get("collect_platform_operational_data")),
            knowledge_allowed_kinds=frozenset(document.get("knowledge_allowed_kinds") or ()),
        )


@dataclass(frozen=True)
class ResourceLimits:
    max_platforms_per_run: int = 8
    max_files_per_platform: int = 5000
    max_inbox_packets: int = 32
    max_seconds_per_platform: int = 120
    max_memory_mb_per_platform: int = 512

    @classmethod
    def load(cls, path: Path) -> ResourceLimits:
        document = json.loads(path.read_text(encoding="utf-8"))
        limits = cls(
            max_platforms_per_run=int(document.get("max_platforms_per_run", 8)),
            max_files_per_platform=int(document.get("max_files_per_platform", 5000)),
            max_inbox_packets=int(document.get("max_inbox_packets", 32)),
            max_seconds_per_platform=int(document.get("max_seconds_per_platform", 120)),
            max_memory_mb_per_platform=int(document.get("max_memory_mb_per_platform", 512)),
        )
        if min(
            limits.max_platforms_per_run,
            limits.max_files_per_platform,
            limits.max_inbox_packets,
            limits.max_seconds_per_platform,
            limits.max_memory_mb_per_platform,
        ) <= 0:
            raise OrchestratorError("INVALID_LIMITS", "resource limits must be positive")
        return limits


@dataclass(frozen=True)
class PlatformAnalysis:
    platform_id: str
    workspace_valid: bool
    path_exists: bool
    analyzed_roots: tuple[str, ...]
    file_count: int
    inventory_digest: str
    pre_improvement_guide: str
    candidate_commit: str | None = None
    error_code: str | None = None
    stage: PlatformStage = PlatformStage.ANALYZED


@dataclass(frozen=True)
class InboxPacket:
    packet_id: str
    stage: InboxStage
    platform_id: str
    created_at: datetime
    summary: str
    production_change_allowed: bool = False
    automatic_learning: bool = False
    payload_digest: str = ""

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": "apf.orchestrator-inbox/v1",
            **{key: (value.value if isinstance(value, Enum) else value) for key, value in asdict(self).items()},
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class OrchestratorState:
    last_run_id: str | None = None
    last_completed_at: str | None = None
    platforms: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestratorRunReport:
    run_id: str
    started_at: datetime
    completed_at: datetime
    foundry_root: Path
    platform_reports: tuple[PlatformAnalysis, ...]
    inbox_packets: tuple[str, ...]
    production_change_allowed: bool = False


class CentralOrchestrator:
    def __init__(
        self,
        *,
        foundry_root: Path,
        policy: SharedPolicy,
        limits: ResourceLimits,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy = policy
        self.limits = limits
        self.clock = clock or (lambda: datetime.now(UTC))
        self.inbox_root = self.foundry_root / "inbox"
        self.reports_root = self.foundry_root / "reports"
        self.logs_root = self.foundry_root / "logs"
        self.quarantine_root = self.foundry_root / "quarantine"
        self.state_root = self.foundry_root / "state"

    @classmethod
    def from_config(cls, foundry_root: Path) -> CentralOrchestrator:
        root = foundry_root.resolve()
        policy = SharedPolicy.load(root / "config" / "shared-policy.json")
        limits = ResourceLimits.load(root / "config" / "resource-limits.json")
        return cls(foundry_root=root, policy=policy, limits=limits)

    @staticmethod
    def load_platforms(config_path: Path, *, foundry_root: Path) -> tuple[PlatformRegistration, ...]:
        document = json.loads(config_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != SCHEMA_PLATFORMS:
            raise OrchestratorError("PLATFORMS_SCHEMA", "unsupported platforms schema")
        configured_root = Path(str(document["foundry_root"])).resolve()
        if configured_root != foundry_root.resolve():
            raise OrchestratorError("FOUNDRY_ROOT_MISMATCH", "platforms.json foundry_root mismatch")
        registrations: list[PlatformRegistration] = []
        for item in document.get("platforms") or []:
            registration = PlatformRegistration(
                platform_id=str(item["id"]),
                path=_normalize_platform_path(Path(str(item["path"])), foundry_root=foundry_root),
                enabled=bool(item.get("enabled", True)),
            )
            registrations.append(registration)
        if not registrations:
            raise OrchestratorError("NO_PLATFORMS", "at least one platform must be registered")
        return tuple(registrations)

    def run(self, registrations: tuple[PlatformRegistration, ...], *, dry_run: bool = False) -> OrchestratorRunReport:
        lock = RunLock(self.state_root / "orchestrator.run.lock")
        if not dry_run:
            lock.acquire()
        try:
            started = self.clock()
            run_id = sha256(f"{started.isoformat()}|{self.foundry_root}".encode()).hexdigest()[:24]
            enabled = tuple(item for item in registrations if item.enabled)[: self.limits.max_platforms_per_run]
            analyses: list[PlatformAnalysis] = []
            packet_paths: list[str] = []
            for registration in enabled:
                analysis = self._analyze_platform_safe(registration)
                analyses.append(analysis)
                if analysis.stage == PlatformStage.BLOCKED:
                    continue
                if len(packet_paths) < self.limits.max_inbox_packets:
                    research_path = self._write_inbox(
                        InboxPacket(
                            packet_id=f"{run_id}-{registration.platform_id}-research",
                            stage=InboxStage.RESEARCH,
                            platform_id=registration.platform_id,
                            created_at=self.clock(),
                            summary=analysis.pre_improvement_guide,
                            payload_digest=analysis.inventory_digest,
                        ),
                        dry_run=dry_run,
                    )
                    if research_path:
                        packet_paths.append(research_path)
                if len(packet_paths) < self.limits.max_inbox_packets:
                    review_path = self._write_inbox(
                        InboxPacket(
                            packet_id=f"{run_id}-{registration.platform_id}-eternian",
                            stage=InboxStage.ETHERNIAN_REVIEW,
                            platform_id=registration.platform_id,
                            created_at=self.clock(),
                            summary=(
                                f"{registration.platform_id}: eternian review required before any code or ops change"
                            ),
                            payload_digest=analysis.inventory_digest,
                        ),
                        dry_run=dry_run,
                    )
                    if review_path:
                        packet_paths.append(review_path)
                if analysis.candidate_commit and len(packet_paths) < self.limits.max_inbox_packets:
                    packet_paths.extend(
                        self._write_experience_proposals(
                            registration=registration,
                            candidate_commit=analysis.candidate_commit,
                            run_id=run_id,
                            dry_run=dry_run,
                            remaining_slots=self.limits.max_inbox_packets - len(packet_paths),
                        )
                    )
            completed = self.clock()
            report = OrchestratorRunReport(
                run_id=run_id,
                started_at=started,
                completed_at=completed,
                foundry_root=self.foundry_root,
                platform_reports=tuple(analyses),
                inbox_packets=tuple(packet_paths),
            )
            if not dry_run:
                self._write_report(report)
                self._write_state(report)
                self._append_log(report)
            return report
        finally:
            if not dry_run:
                lock.release()

    def _analyze_platform_safe(self, registration: PlatformRegistration) -> PlatformAnalysis:
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._analyze_platform, registration)
                return future.result(timeout=self.limits.max_seconds_per_platform)
        except FuturesTimeoutError:
            candidate_commit = _read_candidate_commit(registration.path) if registration.path.is_dir() else None
            return PlatformAnalysis(
                platform_id=registration.platform_id,
                workspace_valid=False,
                path_exists=registration.path.is_dir(),
                analyzed_roots=(),
                file_count=0,
                inventory_digest=sha256(b"timeout").hexdigest(),
                pre_improvement_guide=(
                    f"{registration.platform_id}: analysis timed out after "
                    f"{self.limits.max_seconds_per_platform}s"
                ),
                candidate_commit=candidate_commit,
                error_code="PLATFORM_TIMEOUT",
                stage=PlatformStage.BLOCKED,
            )
        except OrchestratorError as error:
            candidate_commit = _read_candidate_commit(registration.path) if registration.path.is_dir() else None
            return PlatformAnalysis(
                platform_id=registration.platform_id,
                workspace_valid=False,
                path_exists=registration.path.is_dir(),
                analyzed_roots=(),
                file_count=0,
                inventory_digest=sha256(error.code.encode()).hexdigest(),
                pre_improvement_guide=f"{registration.platform_id}: {error}",
                candidate_commit=candidate_commit,
                error_code=error.code,
                stage=PlatformStage.BLOCKED,
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            candidate_commit = _read_candidate_commit(registration.path) if registration.path.is_dir() else None
            return PlatformAnalysis(
                platform_id=registration.platform_id,
                workspace_valid=False,
                path_exists=registration.path.is_dir(),
                analyzed_roots=(),
                file_count=0,
                inventory_digest=sha256(str(error).encode()).hexdigest(),
                pre_improvement_guide=f"{registration.platform_id}: analysis failed: {error}",
                candidate_commit=candidate_commit,
                error_code="PLATFORM_ANALYSIS_FAILURE",
                stage=PlatformStage.BLOCKED,
            )

    def _analyze_platform(self, registration: PlatformRegistration) -> PlatformAnalysis:
        platform_path = registration.path.resolve()
        workspace_path = platform_path / "arkaon.workspace.json"
        candidate_commit = _read_candidate_commit(platform_path) if platform_path.is_dir() else None
        if not platform_path.is_dir():
            return PlatformAnalysis(
                platform_id=registration.platform_id,
                workspace_valid=False,
                path_exists=False,
                analyzed_roots=(),
                file_count=0,
                inventory_digest=sha256(b"missing").hexdigest(),
                pre_improvement_guide=f"{registration.platform_id}: platform path missing; register only explicit folders",
                candidate_commit=candidate_commit,
                stage=PlatformStage.BLOCKED,
            )
        workspace = PlatformWorkspace.load(workspace_path)
        if workspace.platform_id != registration.platform_id:
            raise OrchestratorError("PLATFORM_ID_MISMATCH", "workspace platform_id does not match registration")
        if workspace.foundry_root.resolve() != self.foundry_root:
            raise OrchestratorError("WORKSPACE_FOUNDRY_MISMATCH", "workspace must point to this foundry root")
        inventory: list[str] = []
        file_count = 0
        for root_name in workspace.allowed_analysis_roots:
            root = _resolve_analysis_root(platform_path, root_name)
            if not root.is_dir():
                continue
            for path in _iter_safe_files(platform_path, root):
                relative = path.relative_to(platform_path).as_posix()
                if _matches_forbidden(relative, workspace.forbidden_globs):
                    continue
                if file_count >= self.limits.max_files_per_platform:
                    break
                inventory.append(relative)
                file_count += 1
        digest = sha256("\n".join(inventory).encode()).hexdigest()
        guide = (
            f"{registration.platform_id}: analyzed {file_count} public-structure files across "
            f"{', '.join(workspace.allowed_analysis_roots)}; improvements remain proposal-only"
        )
        return PlatformAnalysis(
            platform_id=registration.platform_id,
            workspace_valid=True,
            path_exists=True,
            analyzed_roots=workspace.allowed_analysis_roots,
            file_count=file_count,
            inventory_digest=digest,
            pre_improvement_guide=guide,
            candidate_commit=candidate_commit,
            stage=PlatformStage.GUIDE_UPDATED,
        )

    def _write_experience_proposals(
        self,
        *,
        registration: PlatformRegistration,
        candidate_commit: str,
        run_id: str,
        dry_run: bool,
        remaining_slots: int,
    ) -> list[str]:
        if remaining_slots <= 0:
            return []
        try:
            proposals = run_platform_experience_audit(
                platform_id=registration.platform_id,
                platform_path=registration.path,
                foundry_root=self.foundry_root,
                candidate_commit=candidate_commit,
                report_id=f"{run_id}-experience",
                now=self.clock(),
            )
        except AuditRejected:
            return []
        paths: list[str] = []
        for proposal in proposals:
            if len(paths) >= remaining_slots:
                break
            paths.append(self._write_experience_proposal(proposal, run_id=run_id, dry_run=dry_run))
        return paths

    def _write_experience_proposal(
        self,
        proposal: ImprovementProposal,
        *,
        run_id: str,
        dry_run: bool,
    ) -> str:
        stage_dir = self.inbox_root / InboxStage.RESEARCH.value
        target = stage_dir / f"{run_id}-{proposal.platform_id}-experience-{proposal.finding.finding_id}.json"
        if dry_run:
            return target.as_posix()
        stage_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(proposal.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target.as_posix()

    def _pending_inbox_paths(self) -> tuple[Path, ...]:
        if not self.inbox_root.is_dir():
            return ()
        return tuple(
            sorted(
                path
                for stage in (
                    InboxStage.RESEARCH,
                    InboxStage.ETHERNIAN_REVIEW,
                    InboxStage.SELF_IMPROVEMENT,
                )
                for path in (self.inbox_root / stage.value).glob("*.json")
                if path.is_file()
            )
        )

    def _find_equivalent_pending(self, packet: InboxPacket) -> Path | None:
        stage_dir = self.inbox_root / packet.stage.value
        if not stage_dir.is_dir():
            return None
        for path in sorted(stage_dir.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                document.get("stage") == packet.stage.value
                and document.get("platform_id") == packet.platform_id
                and document.get("payload_digest") == packet.payload_digest
                and document.get("summary") == packet.summary
            ):
                return path
        return None

    def _record_inbox_backpressure(self, pending_count: int) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        target = self.state_root / "inbox-backpressure.json"
        document = {
            "schema_version": "apf.inbox-backpressure/v1",
            "status": "ACTIVE",
            "observed_at": self.clock().isoformat(),
            "pending_count": pending_count,
            "pending_limit": self.limits.max_inbox_packets,
            "new_packet_created": False,
            "reason": "PENDING_LIMIT_REACHED",
        }
        target.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _write_inbox(self, packet: InboxPacket, *, dry_run: bool = False) -> str | None:
        if packet.stage == InboxStage.OPERATOR_DECISION:
            raise OrchestratorError(
                "INBOX_STAGE_FORBIDDEN",
                "operator-decision requires eternian review first",
            )
        if packet.stage not in (InboxStage.RESEARCH, InboxStage.ETHERNIAN_REVIEW):
            raise OrchestratorError("INBOX_STAGE_FORBIDDEN", f"unsupported inbox stage: {packet.stage.value}")
        if packet.production_change_allowed or packet.automatic_learning:
            raise OrchestratorError("INBOX_FORBIDDEN", "inbox packets must remain propose-only")
        for key in _FORBIDDEN_KNOWLEDGE_KEYS:
            if key in packet.summary.casefold():
                self._quarantine(packet)
                raise OrchestratorError("KNOWLEDGE_BOUNDARY", "summary touched forbidden operational category")
        stage_dir = self.inbox_root / packet.stage.value
        target = stage_dir / f"{packet.packet_id}.json"
        if dry_run:
            return target.as_posix()
        equivalent = self._find_equivalent_pending(packet)
        if equivalent is not None:
            return equivalent.as_posix()
        pending_count = len(self._pending_inbox_paths())
        if pending_count >= self.limits.max_inbox_packets:
            self._record_inbox_backpressure(pending_count)
            return None
        stage_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(packet.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target.as_posix()

    def _quarantine(self, packet: InboxPacket) -> None:
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        target = self.quarantine_root / f"{packet.packet_id}.json"
        target.write_text(json.dumps(packet.to_document(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_report(self, report: OrchestratorRunReport) -> Path:
        day = report.completed_at.astimezone(UTC).strftime("%Y-%m-%d")
        report_dir = self.reports_root / day
        report_dir.mkdir(parents=True, exist_ok=True)
        target = report_dir / f"{report.run_id}.json"
        document = {
            "schema_version": "apf.orchestrator-run-report/v1",
            "run_id": report.run_id,
            "started_at": report.started_at.isoformat(),
            "completed_at": report.completed_at.isoformat(),
            "foundry_root": report.foundry_root.as_posix(),
            "production_change_allowed": report.production_change_allowed,
            "platforms": [
                {
                    "platform_id": item.platform_id,
                    "stage": item.stage.value,
                    "candidate_commit": item.candidate_commit,
                    "file_count": item.file_count,
                    "inventory_digest": item.inventory_digest,
                    "pre_improvement_guide": item.pre_improvement_guide,
                    "error_code": item.error_code,
                }
                for item in report.platform_reports
            ],
            "inbox_packets": list(report.inbox_packets),
        }
        canonical = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        document["report_sha256"] = sha256(canonical.encode()).hexdigest()
        target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return target

    def _write_state(self, report: OrchestratorRunReport) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        state_path = self.state_root / "orchestrator-state.json"
        state = OrchestratorState(
            last_run_id=report.run_id,
            last_completed_at=report.completed_at.isoformat(),
            platforms={item.platform_id: item.stage.value for item in report.platform_reports},
        )
        state_path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_log(self, report: OrchestratorRunReport) -> None:
        self.logs_root.mkdir(parents=True, exist_ok=True)
        day = report.completed_at.astimezone(UTC).strftime("%Y-%m-%d")
        log_path = self.logs_root / f"orchestrator-{day}.log"
        line = (
            f"{report.completed_at.isoformat()} run={report.run_id} "
            f"platforms={len(report.platform_reports)} packets={len(report.inbox_packets)} "
            f"production_change_allowed=false\n"
        )
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
