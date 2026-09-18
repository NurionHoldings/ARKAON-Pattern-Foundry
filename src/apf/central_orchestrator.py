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
from pathlib import Path, PureWindowsPath
from typing import Any

from .accumulation_policy import (
    has_capacity,
    parse_optional_limit,
    remaining_capacity,
    slice_by_limit,
)
from .experience_audit_bridge import run_platform_experience_audit
from .experience_operations_audit import AuditRejected, ImprovementProposal

SCHEMA_PLATFORMS = "apf.central-platforms/v1"
SCHEMA_WORKSPACE = "arkaon.workspace/v1"
_FORBIDDEN_NAME = re.compile(
    r"(^|/)(\.env|secrets?|credentials?|tokens?|certs?|certificates?|pii|personal_data|"
    r"node_modules/|__pycache__/|\.git/)(/|$|\.)",
    re.IGNORECASE,
)
_FORBIDDEN_SUFFIXES = frozenset(
    {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".mdb"}
)
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
    if os.name != "nt" and PureWindowsPath(str(path)).is_absolute():
        return path
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError as exc:
        raise OrchestratorError(
            "PLATFORM_PATH_INVALID", f"cannot resolve platform path: {path}"
        ) from exc
    if not resolved.is_absolute():
        raise OrchestratorError(
            "PLATFORM_PATH_RELATIVE", "platform path must be absolute after normalization"
        )
    try:
        resolved.relative_to(foundry_root.resolve())
    except ValueError:
        return resolved
    raise OrchestratorError(
        "PLATFORM_INSIDE_FOUNDRY", "platform workspace must stay outside foundry root"
    )


def _resolve_analysis_root(platform_path: Path, root_name: str) -> Path:
    if root_name.startswith(("/", "\\")) or ".." in Path(root_name).parts:
        raise OrchestratorError("ANALYSIS_ROOT_ESCAPE", f"unsafe analysis root: {root_name}")
    candidate = (platform_path / root_name).resolve()
    try:
        candidate.relative_to(platform_path.resolve())
    except ValueError as exc:
        raise OrchestratorError(
            "ANALYSIS_ROOT_ESCAPE", f"analysis root escapes platform: {root_name}"
        ) from exc
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
            raise OrchestratorError(
                "PRODUCTION_CHANGE_FORBIDDEN", "workspace cannot allow production changes"
            )
        roots = tuple(document.get("allowed_analysis_roots") or ())
        if not roots:
            raise OrchestratorError(
                "WORKSPACE_ROOTS_REQUIRED", "allowed analysis roots are required"
            )
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
        {
            "public_reference",
            "policy",
            "schema",
            "synthetic_test_pattern",
            "generalized_dev_knowledge",
        }
    )

    @classmethod
    def load(cls, path: Path) -> SharedPolicy:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("automatic_learning") or document.get("production_change_allowed"):
            raise OrchestratorError("POLICY_FORBIDDEN", "central policy must remain propose-only")
        if document.get("collect_platform_operational_data"):
            raise OrchestratorError(
                "OPERATIONAL_DATA_FORBIDDEN", "platform operational data stays isolated"
            )
        return cls(
            automatic_learning=bool(document.get("automatic_learning")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            collect_platform_operational_data=bool(
                document.get("collect_platform_operational_data")
            ),
            knowledge_allowed_kinds=frozenset(document.get("knowledge_allowed_kinds") or ()),
        )


@dataclass(frozen=True)
class ResourceLimits:
    accumulation_mode: str = "bounded"
    max_platforms_per_run: int | None = 8
    max_files_per_platform: int | None = 5000
    max_inbox_packets: int | None = 32
    max_seconds_per_platform: int | None = 120
    max_memory_mb_per_platform: int | None = 512
    sequential_platform_analysis: bool = True
    parallel_platform_workers: int | None = 1

    @property
    def is_unbounded(self) -> bool:
        return self.accumulation_mode == "unbounded"

    @classmethod
    def load(cls, path: Path) -> ResourceLimits:
        document = json.loads(path.read_text(encoding="utf-8"))
        schema = str(document.get("schema_version", "apf.resource-limits/v1"))
        accumulation_mode = str(document.get("accumulation_mode", "bounded")).strip().lower()
        if schema == "apf.resource-limits/v2" or accumulation_mode == "unbounded":
            limits = cls(
                accumulation_mode=accumulation_mode
                if accumulation_mode in {"bounded", "unbounded"}
                else "bounded",
                max_platforms_per_run=parse_optional_limit(
                    document.get("max_platforms_per_run"), default=8
                ),
                max_files_per_platform=parse_optional_limit(
                    document.get("max_files_per_platform"), default=5000
                ),
                max_inbox_packets=parse_optional_limit(
                    document.get("max_inbox_packets"), default=32
                ),
                max_seconds_per_platform=parse_optional_limit(
                    document.get("max_seconds_per_platform"), default=120
                ),
                max_memory_mb_per_platform=parse_optional_limit(
                    document.get("max_memory_mb_per_platform"), default=512
                ),
                sequential_platform_analysis=bool(
                    document.get("sequential_platform_analysis", True)
                ),
                parallel_platform_workers=parse_optional_limit(
                    document.get("parallel_platform_workers"), default=1
                ),
            )
        else:
            limits = cls(
                accumulation_mode="bounded",
                max_platforms_per_run=int(document.get("max_platforms_per_run", 8)),
                max_files_per_platform=int(document.get("max_files_per_platform", 5000)),
                max_inbox_packets=int(document.get("max_inbox_packets", 32)),
                max_seconds_per_platform=int(document.get("max_seconds_per_platform", 120)),
                max_memory_mb_per_platform=int(document.get("max_memory_mb_per_platform", 512)),
                sequential_platform_analysis=bool(
                    document.get("sequential_platform_analysis", True)
                ),
                parallel_platform_workers=parse_optional_limit(
                    document.get("parallel_platform_workers"), default=1
                ),
            )
        positive_limits = [
            value
            for value in (
                limits.max_platforms_per_run,
                limits.max_files_per_platform,
                limits.max_inbox_packets,
                limits.max_seconds_per_platform,
                limits.max_memory_mb_per_platform,
                limits.parallel_platform_workers,
            )
            if value is not None
        ]
        if positive_limits and min(positive_limits) <= 0:
            raise OrchestratorError("INVALID_LIMITS", "resource limits must be positive when set")
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
            **{
                key: (value.value if isinstance(value, Enum) else value)
                for key, value in asdict(self).items()
            },
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
    proposal_quality: dict[str, object] | None = None


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
    def load_platforms(
        config_path: Path, *, foundry_root: Path
    ) -> tuple[PlatformRegistration, ...]:
        document = json.loads(config_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != SCHEMA_PLATFORMS:
            raise OrchestratorError("PLATFORMS_SCHEMA", "unsupported platforms schema")
        configured_value = str(document["foundry_root"])
        configured_root = (
            foundry_root.resolve()
            if configured_value == "${FOUNDRY_ROOT}"
            else Path(configured_value).resolve()
        )
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

    def run(
        self,
        registrations: tuple[PlatformRegistration, ...],
        *,
        dry_run: bool = False,
        demo_map_ops_advisory: bool = False,
    ) -> OrchestratorRunReport:
        lock = RunLock(self.state_root / "orchestrator.run.lock")
        if not dry_run:
            lock.acquire()
        try:
            started = self.clock()
            if not dry_run:
                self._run_predeployment_gate(registrations)
            watch_events = self._collect_research_watch_events(run_id_prefix=started.isoformat())
            watch_paths = self._bridge_research_watch_events(
                watch_events,
                run_id_prefix=started.isoformat(),
                dry_run=dry_run,
            )
            sns_events = self._collect_sns_watch_events(run_id_prefix=started.isoformat())
            sns_paths = self._bridge_sns_watch_events(
                sns_events,
                run_id_prefix=started.isoformat(),
                dry_run=dry_run,
            )
            sns_trend_paths = self._run_sns_trend_analysis(
                run_id_prefix=started.isoformat(),
                dry_run=dry_run,
            )
            market_events = self._collect_emerging_market_events(run_id_prefix=started.isoformat())
            market_paths = self._bridge_emerging_market_events(
                market_events,
                run_id_prefix=started.isoformat(),
                dry_run=dry_run,
            )
            run_id = sha256(f"{started.isoformat()}|{self.foundry_root}".encode()).hexdigest()[:24]
            investigation_paths = self._run_asset_investigation(
                run_id=run_id,
                watch_events=watch_events,
                dry_run=dry_run,
            )
            map_ops_paths = self._run_map_ops_gate(
                run_id=run_id,
                dry_run=dry_run,
                demo_advisory=demo_map_ops_advisory,
            )
            impediment_paths = self._run_learning_impediment(run_id=run_id, dry_run=dry_run)
            intent_repair_paths = self._run_intent_dna_self_repair(run_id=run_id, dry_run=dry_run)
            enabled_all = tuple(item for item in registrations if item.enabled)
            if self.limits.max_platforms_per_run is None:
                enabled = enabled_all
            else:
                enabled = enabled_all[: self.limits.max_platforms_per_run]
            analyses: list[PlatformAnalysis] = []
            packet_paths: list[str] = (
                list(watch_paths)
                + list(sns_paths)
                + list(sns_trend_paths)
                + list(market_paths)
                + list(investigation_paths)
                + list(map_ops_paths)
                + list(impediment_paths)
                + list(intent_repair_paths)
            )
            if self.limits.sequential_platform_analysis:
                for registration in enabled:
                    analysis, extra_paths = self._process_platform_registration(
                        registration=registration,
                        run_id=run_id,
                        dry_run=dry_run,
                        packet_paths=packet_paths,
                    )
                    analyses.append(analysis)
                    packet_paths.extend(extra_paths)
            else:
                worker_count = self.limits.parallel_platform_workers or max(len(enabled), 1)
                with ThreadPoolExecutor(max_workers=worker_count) as pool:
                    parallel_results = list(pool.map(self._analyze_platform_safe, enabled))
                for registration, analysis in zip(enabled, parallel_results, strict=True):
                    analyses.append(analysis)
                    _, extra_paths = self._process_platform_registration(
                        registration=registration,
                        run_id=run_id,
                        dry_run=dry_run,
                        packet_paths=packet_paths,
                        analysis=analysis,
                    )
                    packet_paths.extend(extra_paths)
            resolution_paths = self._run_analysis_target_resolution(
                run_id=run_id,
                registrations=registrations,
                analyses=tuple(analyses),
                dry_run=dry_run,
                packet_count=len(packet_paths),
            )
            packet_paths.extend(resolution_paths)
            completed = self.clock()
            proposal_quality_doc = self._evaluate_proposal_quality(now=completed, dry_run=dry_run)
            report = OrchestratorRunReport(
                run_id=run_id,
                started_at=started,
                completed_at=completed,
                foundry_root=self.foundry_root,
                platform_reports=tuple(analyses),
                inbox_packets=tuple(packet_paths),
                proposal_quality=proposal_quality_doc,
            )
            if not dry_run:
                self._sync_mailbox(completed)
                self._write_report(report)
                self._write_state(report)
                self._append_log(report)
            return report
        finally:
            if not dry_run:
                lock.release()

    def _process_platform_registration(
        self,
        *,
        registration: PlatformRegistration,
        run_id: str,
        dry_run: bool,
        packet_paths: list[str],
        analysis: PlatformAnalysis | None = None,
    ) -> tuple[PlatformAnalysis, list[str]]:
        if analysis is None:
            analysis = self._analyze_platform_safe(registration)
        extra_paths: list[str] = []
        if analysis.stage == PlatformStage.BLOCKED:
            return analysis, extra_paths
        if has_capacity(len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets):
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
                extra_paths.append(research_path)
        if has_capacity(len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets):
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
                extra_paths.append(review_path)
        slots = remaining_capacity(
            len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
        )
        if analysis.candidate_commit and has_capacity(
            len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
        ):
            extra_paths.extend(
                self._write_experience_proposals(
                    registration=registration,
                    candidate_commit=analysis.candidate_commit,
                    run_id=run_id,
                    dry_run=dry_run,
                    remaining_slots=slots,
                )
            )
            slots = remaining_capacity(
                len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
            )
        if analysis.stage != PlatformStage.BLOCKED and has_capacity(
            len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
        ):
            extra_paths.extend(
                self._observe_public_surface(
                    registration=registration,
                    run_id=run_id,
                    dry_run=dry_run,
                    remaining_slots=slots,
                )
            )
            slots = remaining_capacity(
                len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
            )
        if analysis.stage != PlatformStage.BLOCKED and has_capacity(
            len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
        ):
            extra_paths.extend(
                self._run_plaza_governance(
                    registration=registration,
                    run_id=run_id,
                    dry_run=dry_run,
                    remaining_slots=slots,
                )
            )
            slots = remaining_capacity(
                len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
            )
        if analysis.stage != PlatformStage.BLOCKED and has_capacity(
            len(packet_paths) + len(extra_paths), self.limits.max_inbox_packets
        ):
            extra_paths.extend(
                self._run_capability_gap(
                    registration=registration,
                    run_id=run_id,
                    dry_run=dry_run,
                    remaining_slots=slots,
                )
            )
        return analysis, extra_paths

    def _analyze_platform_safe(self, registration: PlatformRegistration) -> PlatformAnalysis:
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._analyze_platform, registration)
                if self.limits.max_seconds_per_platform is None:
                    return future.result()
                return future.result(timeout=self.limits.max_seconds_per_platform)
        except FuturesTimeoutError:
            candidate_commit = (
                _read_candidate_commit(registration.path) if registration.path.is_dir() else None
            )
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
            candidate_commit = (
                _read_candidate_commit(registration.path) if registration.path.is_dir() else None
            )
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
            candidate_commit = (
                _read_candidate_commit(registration.path) if registration.path.is_dir() else None
            )
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
            raise OrchestratorError(
                "PLATFORM_ID_MISMATCH", "workspace platform_id does not match registration"
            )
        if workspace.foundry_root.resolve() != self.foundry_root:
            raise OrchestratorError(
                "WORKSPACE_FOUNDRY_MISMATCH", "workspace must point to this foundry root"
            )
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
                if (
                    self.limits.max_files_per_platform is not None
                    and file_count >= self.limits.max_files_per_platform
                ):
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

    def _run_map_ops_gate(
        self, *, run_id: str, dry_run: bool, demo_advisory: bool = False
    ) -> list[str]:
        from .map_ops_bridge import bridge_map_ops_gate_report
        from .map_ops_gate import EtaShadowObservation, MapOpsGateHarness

        eta_observation = None
        if demo_advisory:
            eta_observation = EtaShadowObservation(
                route_id="demo-advisory-route",
                predicted_duration_s=600,
                observed_duration_s=3600,
            )
        report = MapOpsGateHarness(foundry_root=self.foundry_root).run(
            platform_id="ARKAON_FOUNDRY",
            now=self.clock(),
            eta_observation=eta_observation,
        )
        path = bridge_map_ops_gate_report(
            foundry_root=self.foundry_root,
            report=report,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )
        return [path] if path else []

    def _run_plaza_governance(
        self,
        *,
        registration: PlatformRegistration,
        run_id: str,
        dry_run: bool,
        remaining_slots: int | None,
    ) -> list[str]:
        if remaining_slots is not None and remaining_slots <= 0:
            return []
        from .mobility_plaza_bridge import bridge_plaza_governance_report
        from .mobility_plaza_governance import PlazaGovernanceHarness

        harness = PlazaGovernanceHarness(foundry_root=self.foundry_root)
        report = harness.audit_platform_config(
            platform_id=registration.platform_id,
            platform_path=registration.path,
            now=self.clock(),
        )
        if report is None:
            return []
        path = bridge_plaza_governance_report(
            foundry_root=self.foundry_root,
            report=report,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )
        return [path] if path else []

    def _run_predeployment_gate(self, registrations: tuple[PlatformRegistration, ...]) -> None:
        from .predeployment_readiness import PredeploymentReadinessHarness

        PredeploymentReadinessHarness(foundry_root=self.foundry_root).run(
            now=self.clock(),
            registrations=registrations,
        )

    def _collect_research_watch_events(self, *, run_id_prefix: str) -> tuple:
        from .research_watch import ResearchWatchRegistry

        del run_id_prefix
        registry = ResearchWatchRegistry(foundry_root=self.foundry_root)
        return registry.detect_changes(now=self.clock())

    def _bridge_research_watch_events(
        self, events: tuple, *, run_id_prefix: str, dry_run: bool
    ) -> list[str]:
        from .research_watch_bridge import bridge_research_watch_events

        run_id = sha256(run_id_prefix.encode()).hexdigest()[:24]
        return list(
            bridge_research_watch_events(
                foundry_root=self.foundry_root,
                events=events,
                run_id=run_id,
                now=self.clock(),
                dry_run=dry_run,
            )
        )

    def _run_research_watch(self, *, run_id_prefix: str, dry_run: bool) -> list[str]:
        events = self._collect_research_watch_events(run_id_prefix=run_id_prefix)
        return self._bridge_research_watch_events(
            events, run_id_prefix=run_id_prefix, dry_run=dry_run
        )

    def _collect_sns_watch_events(self, *, run_id_prefix: str) -> tuple:
        from .sns_watch import SNSWatchRegistry

        del run_id_prefix
        registry = SNSWatchRegistry(foundry_root=self.foundry_root)
        return registry.analyze(now=self.clock())

    def _bridge_sns_watch_events(
        self, events: tuple, *, run_id_prefix: str, dry_run: bool
    ) -> list[str]:
        from .sns_watch_bridge import bridge_sns_watch_events

        run_id = sha256(run_id_prefix.encode()).hexdigest()[:24]
        return list(
            bridge_sns_watch_events(
                foundry_root=self.foundry_root,
                events=events,
                run_id=run_id,
                now=self.clock(),
                dry_run=dry_run,
            )
        )

    def _run_analysis_target_resolution(
        self,
        *,
        run_id: str,
        registrations: tuple[PlatformRegistration, ...],
        analyses: tuple[PlatformAnalysis, ...],
        dry_run: bool,
        packet_count: int,
    ) -> list[str]:
        if not has_capacity(packet_count, self.limits.max_inbox_packets):
            return []
        from .analysis_target_resolution import AnalysisTargetResolutionEngine
        from .analysis_target_resolution_bridge import bridge_analysis_target_resolution_report

        enabled = tuple(item for item in registrations if item.enabled)
        registered_ids = frozenset(item.platform_id for item in registrations)
        enabled_paths_missing = bool(enabled) and all(not item.path.is_dir() for item in enabled)
        all_blocked = bool(analyses) and all(item.stage == PlatformStage.BLOCKED for item in analyses)
        engine = AnalysisTargetResolutionEngine(foundry_root=self.foundry_root)
        try:
            report = engine.analyze(
                now=self.clock(),
                run_id=run_id,
                dry_run=dry_run,
                enabled_registration_count=len(enabled),
                enabled_paths_missing=enabled_paths_missing,
                registered_platform_ids=registered_ids,
                all_platforms_blocked=all_blocked,
            )
        except (OSError, ValueError):
            return []
        paths = bridge_analysis_target_resolution_report(
            foundry_root=self.foundry_root,
            report=report,
            policy=engine.policy,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )
        paths.extend(
            self._run_cross_platform_learning(
                resolution_report=report,
                run_id=run_id,
                dry_run=dry_run,
                packet_count=packet_count + len(paths),
            )
        )
        return paths

    def _run_cross_platform_learning(
        self,
        *,
        resolution_report,
        run_id: str,
        dry_run: bool,
        packet_count: int,
    ) -> list[str]:
        if not has_capacity(packet_count, self.limits.max_inbox_packets):
            return []
        from .cross_platform_learning import CrossPlatformLearningEngine
        from .cross_platform_learning_bridge import bridge_cross_platform_learning_report

        engine = CrossPlatformLearningEngine(foundry_root=self.foundry_root)
        try:
            report = engine.execute(
                resolution_report=resolution_report,
                now=self.clock(),
                dry_run=dry_run,
            )
        except (OSError, ValueError):
            return []
        return bridge_cross_platform_learning_report(
            foundry_root=self.foundry_root,
            report=report,
            policy=engine.policy,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )

    def _run_intent_dna_self_repair(self, *, run_id: str, dry_run: bool) -> list[str]:
        from .intent_dna_self_repair import IntentDnaSelfRepairEngine
        from .intent_dna_self_repair_bridge import bridge_intent_dna_self_repair_report

        engine = IntentDnaSelfRepairEngine(foundry_root=self.foundry_root)
        report = engine.analyze(now=self.clock(), dry_run=dry_run)
        return bridge_intent_dna_self_repair_report(
            foundry_root=self.foundry_root,
            report=report,
            policy=engine.policy,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )

    def _run_learning_impediment(self, *, run_id: str, dry_run: bool) -> list[str]:
        from .learning_impediment import EngineLimitSnapshot, LearningImpedimentEngine
        from .learning_impediment_bridge import bridge_learning_impediment_report

        engine = LearningImpedimentEngine(foundry_root=self.foundry_root)
        snapshot = EngineLimitSnapshot(
            is_unbounded=self.limits.is_unbounded,
            max_inbox_packets=self.limits.max_inbox_packets,
            max_platforms_per_run=self.limits.max_platforms_per_run,
            max_files_per_platform=self.limits.max_files_per_platform,
            max_seconds_per_platform=self.limits.max_seconds_per_platform,
        )
        report = engine.analyze(now=self.clock(), limits=snapshot)
        return bridge_learning_impediment_report(
            foundry_root=self.foundry_root,
            report=report,
            policy=engine.policy,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )

    def _run_sns_trend_analysis(self, *, run_id_prefix: str, dry_run: bool) -> list[str]:
        from .sns_attention_analysis import SNSAttentionAnalyzer, SNSAttentionPolicy
        from .sns_attention_bridge import bridge_sns_attention_report
        from .sns_trend_analysis import SNSTrendAnalyzer
        from .sns_trend_bridge import bridge_sns_trend_report

        run_id = sha256(run_id_prefix.encode()).hexdigest()[:24]
        report = SNSTrendAnalyzer(foundry_root=self.foundry_root).analyze(now=self.clock())
        paths = list(
            bridge_sns_trend_report(
                foundry_root=self.foundry_root,
                report=report,
                run_id=run_id,
                now=self.clock(),
                dry_run=dry_run,
            )
        )
        attention_policy = SNSAttentionPolicy.load(
            self.foundry_root / "config" / "arkaon-sns-attention.json"
        )
        if attention_policy.enabled and report.surge_items:
            attention_report = SNSAttentionAnalyzer(
                foundry_root=self.foundry_root,
                policy=attention_policy,
            ).analyze_surge_items(surge_items=report.surge_items, now=self.clock())
            paths.extend(
                bridge_sns_attention_report(
                    foundry_root=self.foundry_root,
                    report=attention_report,
                    run_id=run_id,
                    now=self.clock(),
                    dry_run=dry_run,
                    emit_inbox_packets=attention_policy.emit_inbox_packets,
                )
            )
        return paths

    def _collect_emerging_market_events(self, *, run_id_prefix: str) -> tuple:
        from .emerging_market_watch import EmergingMarketWatchRegistry

        del run_id_prefix
        registry = EmergingMarketWatchRegistry(foundry_root=self.foundry_root)
        return registry.analyze(now=self.clock())

    def _bridge_emerging_market_events(
        self, events: tuple, *, run_id_prefix: str, dry_run: bool
    ) -> list[str]:
        from .emerging_market_watch_bridge import bridge_emerging_market_events

        run_id = sha256(run_id_prefix.encode()).hexdigest()[:24]
        return list(
            bridge_emerging_market_events(
                foundry_root=self.foundry_root,
                events=events,
                run_id=run_id,
                now=self.clock(),
                dry_run=dry_run,
            )
        )

    def _sync_mailbox(self, now: datetime) -> None:
        from .arkaon_mailbox import ArkaonMailbox, MailboxRejected

        try:
            ArkaonMailbox(foundry_root=self.foundry_root).sync_from_inbox(now=now)
        except (MailboxRejected, OSError, ValueError, TypeError):
            return

    def _run_capability_gap(
        self,
        *,
        registration: PlatformRegistration,
        run_id: str,
        dry_run: bool,
        remaining_slots: int | None,
    ) -> list[str]:
        if remaining_slots is not None and remaining_slots <= 0:
            return []
        from .capability_gap import CapabilityGapEngine, CapabilityGapRejected
        from .capability_gap_bridge import bridge_capability_gap_report

        engine = CapabilityGapEngine(foundry_root=self.foundry_root)
        try:
            report = engine.analyze_owned_platform(
                owned_platform_id=registration.platform_id,
                owned_platform_path=registration.path,
                now=self.clock(),
            )
        except (CapabilityGapRejected, OSError, ValueError):
            return []
        if not dry_run:
            engine.persist(report)
        bridged = bridge_capability_gap_report(
            foundry_root=self.foundry_root,
            report=report,
            policy=engine.policy,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )
        return list(slice_by_limit(tuple(bridged), remaining_slots))

    def _run_asset_investigation(
        self,
        *,
        run_id: str,
        watch_events: tuple,
        dry_run: bool,
    ) -> list[str]:
        from .asset_investigation import AssetInvestigationHarness
        from .asset_investigation_bridge import bridge_asset_investigation_report

        harness = AssetInvestigationHarness(foundry_root=self.foundry_root)
        report = harness.run(now=self.clock(), watch_events=watch_events)
        if not dry_run:
            harness.persist(report)
        path = bridge_asset_investigation_report(
            foundry_root=self.foundry_root,
            report=report,
            policy=harness.policy,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )
        return [path] if path else []

    def _observe_public_surface(
        self,
        *,
        registration: PlatformRegistration,
        run_id: str,
        dry_run: bool,
        remaining_slots: int | None,
    ) -> list[str]:
        if remaining_slots is not None and remaining_slots <= 0:
            return []
        from .public_surface_bridge import bridge_public_surface_observation
        from .public_surface_observer import observe_public_surface

        try:
            report = observe_public_surface(
                platform_id=registration.platform_id,
                platform_path=registration.path,
                foundry_root=self.foundry_root,
                now=self.clock(),
            )
        except (OSError, ValueError):
            return []
        inbox_path, _ = bridge_public_surface_observation(
            foundry_root=self.foundry_root,
            report=report,
            run_id=run_id,
            now=self.clock(),
            dry_run=dry_run,
        )
        return [inbox_path]

    def _write_experience_proposals(
        self,
        *,
        registration: PlatformRegistration,
        candidate_commit: str,
        run_id: str,
        dry_run: bool,
        remaining_slots: int | None,
    ) -> list[str]:
        if remaining_slots is not None and remaining_slots <= 0:
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
        bridged: list[ImprovementProposal] = []
        for proposal in proposals:
            if remaining_slots is not None and len(paths) >= remaining_slots:
                break
            paths.append(self._write_experience_proposal(proposal, run_id=run_id, dry_run=dry_run))
            bridged.append(proposal)
        if bridged and (remaining_slots is None or len(paths) < remaining_slots):
            from .reflection_bridge import bridge_experience_proposals

            bridge_slots = None if remaining_slots is None else remaining_slots - len(paths)
            bridge_results = bridge_experience_proposals(
                foundry_root=self.foundry_root,
                proposals=tuple(slice_by_limit(tuple(bridged), bridge_slots)),
                run_id=run_id,
                now=self.clock(),
                dry_run=dry_run,
            )
            paths.extend(item[1] for item in bridge_results)
        return paths

    def _write_experience_proposal(
        self,
        proposal: ImprovementProposal,
        *,
        run_id: str,
        dry_run: bool,
    ) -> str:
        stage_dir = self.inbox_root / InboxStage.RESEARCH.value
        target = (
            stage_dir
            / f"{run_id}-{proposal.platform_id}-experience-{proposal.finding.finding_id}.json"
        )
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
            raise OrchestratorError(
                "INBOX_STAGE_FORBIDDEN", f"unsupported inbox stage: {packet.stage.value}"
            )
        if packet.production_change_allowed or packet.automatic_learning:
            raise OrchestratorError("INBOX_FORBIDDEN", "inbox packets must remain propose-only")
        for key in _FORBIDDEN_KNOWLEDGE_KEYS:
            if key in packet.summary.casefold():
                self._quarantine(packet)
                raise OrchestratorError(
                    "KNOWLEDGE_BOUNDARY", "summary touched forbidden operational category"
                )
        stage_dir = self.inbox_root / packet.stage.value
        target = stage_dir / f"{packet.packet_id}.json"
        if dry_run:
            return target.as_posix()
        equivalent = self._find_equivalent_pending(packet)
        if equivalent is not None:
            return equivalent.as_posix()
        pending_count = len(self._pending_inbox_paths())
        if not has_capacity(pending_count, self.limits.max_inbox_packets):
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
        target.write_text(
            json.dumps(packet.to_document(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _evaluate_proposal_quality(
        self,
        *,
        now: datetime,
        dry_run: bool,
    ) -> dict[str, object]:
        from .proposal_quality_score import ProposalQualityScorer

        scorer = ProposalQualityScorer(foundry_root=self.foundry_root)
        if dry_run:
            return scorer.evaluate(now=now).to_document()
        return scorer.evaluate_and_persist(now=now).to_document()

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
            "proposal_quality": report.proposal_quality,
        }
        canonical = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        document["report_sha256"] = sha256(canonical.encode()).hexdigest()
        target.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        return target

    def _write_state(self, report: OrchestratorRunReport) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        state_path = self.state_root / "orchestrator-state.json"
        state = OrchestratorState(
            last_run_id=report.run_id,
            last_completed_at=report.completed_at.isoformat(),
            platforms={item.platform_id: item.stage.value for item in report.platform_reports},
        )
        state_path.write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8"
        )

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


def classify_inbox_packet_path(path: str) -> str:
    """Classify a planned or written inbox packet path for dry-run reporting."""
    normalized = path.replace("\\", "/").lower()
    name = Path(path).name.lower()
    if "-map-ops" in name:
        return "map_ops_gate"
    if "-plaza-gov" in name:
        return "plaza_governance"
    if "-surface" in name:
        return "public_surface"
    if "-experience" in name:
        return "experience_audit"
    if "-watch" in name:
        return "research_watch"
    if "-asset-investigation" in name:
        return "asset_investigation"
    if "-learning-impediment" in name:
        return "learning_impediment"
    if "/eternian-review/" in normalized:
        if "-eternian" in name:
            return "platform_eternian_review"
        return "eternian_review"
    if "/research/" in normalized and "-research" in name:
        return "platform_research"
    return "unknown"
