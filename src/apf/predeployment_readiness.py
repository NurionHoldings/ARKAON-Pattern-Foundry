"""Predeployment readiness gate for Foundry and registered platforms before live startup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .admin_change_control import AdminChangeControlPolicy
from .central_orchestrator import CentralOrchestrator, OrchestratorError, PlatformRegistration
from .emerging_market_watch import EmergingMarketWatchPolicy
from .map_ops_gate import MapOpsGatePolicy
from .mobility_plaza_governance import MobilityPlazaGovernancePolicy
from .public_surface_observer import PublicSurfaceObservationPolicy
from .research_watch import ResearchWatchPolicy
from .sns_watch import SNSWatchPolicy


class PredeployRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class PredeploymentReadinessPolicy:
    automatic_deploy_allowed: bool = False
    production_change_allowed: bool = False
    mandatory_checks: frozenset[str] = frozenset()

    @classmethod
    def load(cls, path: Path) -> PredeploymentReadinessPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-predeployment-readiness/v1":
            raise PredeployRejected("POLICY_SCHEMA", "unsupported predeployment readiness schema")
        if document.get("automatic_deploy_allowed") or document.get("production_change_allowed"):
            raise PredeployRejected("POLICY_FORBIDDEN", "predeployment gate must remain non-deploy")
        return cls(
            automatic_deploy_allowed=bool(document.get("automatic_deploy_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            mandatory_checks=frozenset(document.get("mandatory_checks") or ()),
        )


@dataclass(frozen=True)
class PredeployCheckResult:
    check_id: str
    status: CheckStatus
    message: str


@dataclass(frozen=True)
class PredeploymentReport:
    foundry_root: Path
    evaluated_at: datetime
    results: tuple[PredeployCheckResult, ...]
    overall: CheckStatus
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.predeployment-readiness-report/v1",
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "overall": self.overall.value,
            "report_digest": self.report_digest,
            "results": [
                {"check_id": item.check_id, "status": item.status.value, "message": item.message}
                for item in self.results
            ],
        }


class PredeploymentReadinessHarness:
    """Runs mandatory local checks before orchestrator startup or platform connection."""

    def __init__(self, *, foundry_root: Path, policy: PredeploymentReadinessPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-predeployment-readiness.json"
        self.policy = policy or PredeploymentReadinessPolicy.load(config)
        self.store_root = self.foundry_root / "state" / "predeployment-readiness"
        self.store_root.mkdir(parents=True, exist_ok=True)

    def run(self, *, now: datetime, registrations: tuple[PlatformRegistration, ...] = ()) -> PredeploymentReport:
        if now.tzinfo is None:
            raise PredeployRejected("TIMESTAMP", "timezone-aware timestamp required")
        checks = [
            self._check_shared_policy,
            self._check_resource_limits,
            self._check_accumulation_policy,
            self._check_learning_impediment_policy,
            self._check_platforms_registry,
            self._check_admin_change_control,
            self._check_public_surface_policy,
            self._check_research_watch_policy,
            self._check_sns_watch_policy,
            self._check_emerging_market_watch_policy,
            self._check_reflective_learning_policy,
            self._check_experience_audit_policy,
            self._check_inbox_directories,
            self._check_state_directories,
            self._check_mobility_plaza_governance,
            self._check_map_ops_gate,
        ]
        results: list[PredeployCheckResult] = []
        for checker in checks:
            check_id = checker.__name__.removeprefix("_check_").upper()
            if self.policy.mandatory_checks and check_id not in self.policy.mandatory_checks:
                results.append(PredeployCheckResult(check_id, CheckStatus.SKIP, "not mandatory"))
                continue
            try:
                message = checker(registrations)
                results.append(PredeployCheckResult(check_id, CheckStatus.PASS, message))
            except (PredeployRejected, OrchestratorError) as error:
                results.append(PredeployCheckResult(check_id, CheckStatus.FAIL, str(error)))
        overall = CheckStatus.PASS if all(item.status != CheckStatus.FAIL for item in results) else CheckStatus.FAIL
        document = {
            "foundry_root": self.foundry_root.as_posix(),
            "evaluated_at": now.isoformat(),
            "overall": overall.value,
            "results": [item.__dict__ for item in results],
        }
        report_digest = sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        report = PredeploymentReport(self.foundry_root, now, tuple(results), overall, report_digest)
        target = self.store_root / f"{now.strftime('%Y-%m-%d')}-{report_digest[:16]}.json"
        target.write_text(json.dumps(report.to_document(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        if overall is CheckStatus.FAIL:
            raise PredeployRejected("PREDEPLOY_FAILED", "mandatory predeployment checks failed")
        return report

    def _require_file(self, relative: str) -> Path:
        path = self.foundry_root / relative
        if not path.is_file():
            raise PredeployRejected("MISSING_FILE", f"missing {relative}")
        return path

    def _check_shared_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        CentralOrchestrator.from_config(self.foundry_root)
        return "shared policy loaded"

    def _check_resource_limits(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        self._require_file("config/resource-limits.json")
        return "resource limits present"

    def _check_accumulation_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        from .accumulation_policy import AccumulationPolicy

        AccumulationPolicy.load(self.foundry_root / "config" / "arkaon-accumulation-policy.json")
        return "accumulation policy valid"

    def _check_learning_impediment_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        from .learning_impediment import LearningImpedimentPolicy

        LearningImpedimentPolicy.load(self.foundry_root / "config" / "arkaon-learning-impediment.json")
        return "learning impediment policy valid"

    def _check_platforms_registry(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        path = self._require_file("config/platforms.json")
        CentralOrchestrator.load_platforms(path, foundry_root=self.foundry_root)
        return "platforms registry valid"

    def _check_admin_change_control(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        AdminChangeControlPolicy.load(self.foundry_root / "config" / "arkaon-admin-change-control.json")
        return "admin change control policy valid"

    def _check_public_surface_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        PublicSurfaceObservationPolicy.load(
            self.foundry_root / "config" / "arkaon-public-surface-observation.json"
        )
        return "public surface observation policy valid"

    def _check_research_watch_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        ResearchWatchPolicy.load(self.foundry_root / "config" / "arkaon-research-watch.json")
        self._require_file("config/research-watch-sources.json")
        return "research watch policy valid"

    def _check_sns_watch_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        SNSWatchPolicy.load(self.foundry_root / "config" / "arkaon-sns-watch.json")
        self._require_file("config/sns-watch-sources.json")
        return "sns watch policy valid"

    def _check_emerging_market_watch_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        EmergingMarketWatchPolicy.load(self.foundry_root / "config" / "arkaon-emerging-market-watch.json")
        self._require_file("config/emerging-market-sources.json")
        return "emerging market watch policy valid"

    def _check_reflective_learning_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        document = json.loads(self._require_file("config/arkaon-reflective-learning-policy.json").read_text(encoding="utf-8"))
        if document.get("automatic_operational_application") or document.get("self_approval"):
            raise PredeployRejected("REFLECTIVE_POLICY", "reflective learning must remain governed")
        return "reflective learning policy valid"

    def _check_experience_audit_policy(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        path = self.foundry_root / "config" / "arkaon-experience-operations-audit.json"
        if path.is_file():
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("automatic_change_allowed"):
                raise PredeployRejected("EXPERIENCE_POLICY", "experience audit must remain proposal-only")
        return "experience audit policy valid"

    def _check_inbox_directories(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        for name in ("research", "eternian-review", "operator-decision"):
            (self.foundry_root / "inbox" / name).mkdir(parents=True, exist_ok=True)
        return "inbox directories ready"

    def _check_state_directories(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        for name in (
            "change-control",
            "surface-observations",
            "research-watch",
            "predeployment-readiness",
            "plaza-governance",
            "map-ops-gate",
            "postgres-live-proof",
            "owned-platform-live",
            "reuse-proof-measurement",
            "capability-gap",
            "learning-impediment",
            "mailbox",
        ):
            (self.foundry_root / "state" / name).mkdir(parents=True, exist_ok=True)
        return "state directories ready"

    def _check_mobility_plaza_governance(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        MobilityPlazaGovernancePolicy.load(
            self.foundry_root / "config" / "arkaon-mobility-plaza-governance.json"
        )
        return "mobility plaza governance policy valid"

    def _check_map_ops_gate(self, registrations: tuple[PlatformRegistration, ...]) -> str:
        del registrations
        MapOpsGatePolicy.load(self.foundry_root / "config" / "arkaon-map-ops-gate.json")
        self._require_file("config/map-competency-profile.json")
        self._require_file("config/map-provider-knowledge.provisional.json")
        return "map ops gate policy valid"
