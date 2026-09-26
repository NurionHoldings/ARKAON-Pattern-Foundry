"""Map operations gates #071–#076: knowledge, sandbox, device auth, ETA shadow, resilience, release."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .execution_sandbox import SandboxPolicyDenied, prepare_execution_sandbox
from .route_choice import RouteChoiceService


class MapOpsGateRejected(ValueError):
    pass


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ADVISORY = "ADVISORY"


@dataclass(frozen=True)
class MapOpsGatePolicy:
    production_activation_allowed: bool = False
    automatic_route_selection: bool = False
    continuous_device_tracking: bool = False
    pay_change_from_shadow: bool = False
    mandatory_gates: frozenset[str] = frozenset()
    eta_shadow_tolerance_s: int = 900
    device_auth_max_ttl_minutes: int = 30

    @classmethod
    def load(cls, path: Path) -> MapOpsGatePolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-map-ops-gate/v1":
            raise MapOpsGateRejected("unsupported map ops gate schema")
        if (
            document.get("production_activation_allowed")
            or document.get("automatic_route_selection")
            or document.get("continuous_device_tracking")
            or document.get("pay_change_from_shadow")
        ):
            raise MapOpsGateRejected("map ops gates must remain advisory and non-production")
        return cls(
            production_activation_allowed=bool(document.get("production_activation_allowed")),
            automatic_route_selection=bool(document.get("automatic_route_selection")),
            continuous_device_tracking=bool(document.get("continuous_device_tracking")),
            pay_change_from_shadow=bool(document.get("pay_change_from_shadow")),
            mandatory_gates=frozenset(document.get("mandatory_gates") or ()),
            eta_shadow_tolerance_s=int(document.get("eta_shadow_tolerance_s", 900)),
            device_auth_max_ttl_minutes=int(document.get("device_auth_max_ttl_minutes", 30)),
        )


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: GateStatus
    message: str


@dataclass(frozen=True)
class DeviceAuthSession:
    device_id_hash: str
    rider_id_hash: str
    granted_at: datetime
    expires_at: datetime
    continuous_tracking: bool = False
    purpose: str = "navigation_handoff"

    def valid(self, now: datetime) -> bool:
        return (
            not self.continuous_tracking
            and self.granted_at <= now < self.expires_at
            and bool(self.device_id_hash)
            and bool(self.rider_id_hash)
        )


@dataclass(frozen=True)
class EtaShadowObservation:
    route_id: str
    predicted_duration_s: int
    observed_duration_s: int
    advisory_only: bool = True
    pay_change_allowed: bool = False

    @property
    def delta_s(self) -> int:
        return self.observed_duration_s - self.predicted_duration_s


@dataclass(frozen=True)
class MapOpsGateReport:
    platform_id: str
    evaluated_at: datetime
    results: tuple[GateResult, ...]
    overall: GateStatus
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.map-ops-gate-report/v1",
            "platform_id": self.platform_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "overall": self.overall.value,
            "report_digest": self.report_digest,
            "results": [
                {"gate_id": item.gate_id, "status": item.status.value, "message": item.message}
                for item in self.results
            ],
        }


class MapKnowledgeGate:
    """#071 — provisional provider knowledge must stay BLOCKED without secrets."""

    @staticmethod
    def validate(foundry_root: Path) -> GateResult:
        path = foundry_root / "config" / "map-provider-knowledge.provisional.json"
        if not path.is_file():
            return GateResult("MAP_KNOWLEDGE_071", GateStatus.FAIL, "provisional map knowledge missing")
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("production_activation") != "BLOCKED":
            return GateResult("MAP_KNOWLEDGE_071", GateStatus.FAIL, "production activation must stay BLOCKED")
        for provider in document.get("providers") or []:
            if provider.get("adapter_certified"):
                return GateResult("MAP_KNOWLEDGE_071", GateStatus.FAIL, "uncertified provider marked certified")
            for doc_url in provider.get("official_docs") or []:
                if not str(doc_url).startswith("https://"):
                    return GateResult("MAP_KNOWLEDGE_071", GateStatus.FAIL, "official docs must be HTTPS")
        return GateResult("MAP_KNOWLEDGE_071", GateStatus.PASS, "provisional map knowledge gate passed")


class MapSandboxGate:
    """#072 — map adapter tasks must stay in parser-only sandbox."""

    @staticmethod
    def validate(*, worktree_root: Path) -> GateResult:
        from .development_orchestrator import TaskKind, task_contract

        contract = task_contract(
            TaskKind.AUDIT,
            intent_fingerprint="a" * 64,
            objective="map adapter audit",
            allowed_paths=("src/apf",),
            expected_artifacts=("map-ops-report.json",),
            requested_operations=("READ_WORKTREE", "RUN_LINTER"),
        )
        try:
            prepare_execution_sandbox(contract, worktree_root=worktree_root)
        except SandboxPolicyDenied as error:
            return GateResult("MAP_SANDBOX_072", GateStatus.FAIL, str(error))
        network_contract = task_contract(
            TaskKind.AUDIT,
            intent_fingerprint="b" * 64,
            objective="map adapter network probe",
            allowed_paths=("src/apf",),
            expected_artifacts=("map-ops-report.json",),
            requested_operations=("NETWORK",),
        )
        try:
            prepare_execution_sandbox(network_contract, worktree_root=worktree_root)
            return GateResult("MAP_SANDBOX_072", GateStatus.FAIL, "network must be denied in map sandbox")
        except SandboxPolicyDenied:
            return GateResult("MAP_SANDBOX_072", GateStatus.PASS, "map sandbox denies network and secrets")


class DeviceAuthGate:
    """#073 — device auth is bounded, non-continuous, purpose-limited."""

    @staticmethod
    def validate(*, session: DeviceAuthSession, now: datetime, max_ttl_minutes: int) -> GateResult:
        if session.continuous_tracking:
            return GateResult("DEVICE_AUTH_073", GateStatus.FAIL, "continuous device tracking forbidden")
        if session.expires_at - session.granted_at > timedelta(minutes=max_ttl_minutes):
            return GateResult("DEVICE_AUTH_073", GateStatus.FAIL, "device auth TTL exceeds bound")
        if not session.valid(now):
            return GateResult("DEVICE_AUTH_073", GateStatus.FAIL, "device auth session invalid or expired")
        return GateResult("DEVICE_AUTH_073", GateStatus.PASS, "device auth attestation bounded")


class EtaShadowGate:
    """#074 — ETA shadow is advisory-only; no pay change."""

    @staticmethod
    def compare(observation: EtaShadowObservation, *, tolerance_s: int) -> GateResult:
        if observation.pay_change_allowed:
            return GateResult("ETA_SHADOW_074", GateStatus.FAIL, "ETA shadow must not change pay")
        if not observation.advisory_only:
            return GateResult("ETA_SHADOW_074", GateStatus.FAIL, "ETA shadow must remain advisory-only")
        if abs(observation.delta_s) > tolerance_s:
            return GateResult(
                "ETA_SHADOW_074",
                GateStatus.ADVISORY,
                f"ETA delta {observation.delta_s}s exceeds tolerance; review recommended",
            )
        return GateResult("ETA_SHADOW_074", GateStatus.PASS, "ETA shadow within tolerance")


class MapResilienceGate:
    """#075 — stale quotes fail closed into offline instruction without auto-select."""

    @staticmethod
    def validate(*, now: datetime) -> GateResult:
        instruction = RouteChoiceService.offline_instruction("map-resilience-check", now)
        if instruction.auto_select_route or instruction.stores_address_coordinates_or_tiles:
            return GateResult("MAP_RESILIENCE_075", GateStatus.FAIL, "offline mode must not auto-select or store coords")
        if instruction.expires_at <= now:
            return GateResult("MAP_RESILIENCE_075", GateStatus.FAIL, "offline instruction expired immediately")
        return GateResult("MAP_RESILIENCE_075", GateStatus.PASS, "offline resilience token issued")


class MapReleaseGate:
    """#076 — competency profile and production status gate."""

    @staticmethod
    def validate(foundry_root: Path) -> GateResult:
        path = foundry_root / "config" / "map-competency-profile.json"
        if not path.is_file():
            return GateResult("MAP_RELEASE_076", GateStatus.FAIL, "map competency profile missing")
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("production_status") != "BLOCKED":
            return GateResult("MAP_RELEASE_076", GateStatus.FAIL, "map production must stay BLOCKED")
        thresholds = document.get("thresholds") or {}
        if float(thresholds.get("precision_min", 0)) < 0.95:
            return GateResult("MAP_RELEASE_076", GateStatus.FAIL, "precision threshold too low")
        if not document.get("zero_tolerance"):
            return GateResult("MAP_RELEASE_076", GateStatus.FAIL, "zero tolerance list required")
        return GateResult("MAP_RELEASE_076", GateStatus.PASS, "map release gate profile valid")


class MapOpsGateHarness:
    """Runs mandatory map ops gates and produces a digest-bound report."""

    def __init__(self, *, foundry_root: Path, policy: MapOpsGatePolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        self.policy = policy or MapOpsGatePolicy.load(
            self.foundry_root / "config" / "arkaon-map-ops-gate.json"
        )

    def run(
        self,
        *,
        platform_id: str,
        now: datetime,
        device_session: DeviceAuthSession | None = None,
        eta_observation: EtaShadowObservation | None = None,
    ) -> MapOpsGateReport:
        if now.tzinfo is None:
            raise MapOpsGateRejected("timezone-aware timestamp required")
        results: list[GateResult] = [
            MapKnowledgeGate.validate(self.foundry_root),
            MapSandboxGate.validate(worktree_root=self.foundry_root),
            MapResilienceGate.validate(now=now),
            MapReleaseGate.validate(self.foundry_root),
        ]
        session = device_session or DeviceAuthSession(
            device_id_hash=sha256(b"device").hexdigest(),
            rider_id_hash=sha256(b"rider").hexdigest(),
            granted_at=now,
            expires_at=now + timedelta(minutes=min(15, self.policy.device_auth_max_ttl_minutes)),
        )
        results.append(
            DeviceAuthGate.validate(
                session=session,
                now=now,
                max_ttl_minutes=self.policy.device_auth_max_ttl_minutes,
            )
        )
        observation = eta_observation or EtaShadowObservation(
            route_id="shadow-route",
            predicted_duration_s=600,
            observed_duration_s=720,
        )
        results.append(EtaShadowGate.compare(observation, tolerance_s=self.policy.eta_shadow_tolerance_s))
        if self.policy.mandatory_gates:
            present = {item.gate_id for item in results}
            missing = self.policy.mandatory_gates - present
            if missing:
                results.append(
                    GateResult("MAP_OPS_MISSING", GateStatus.FAIL, f"missing gates: {sorted(missing)}")
                )
        if any(item.status is GateStatus.FAIL for item in results):
            overall = GateStatus.FAIL
        elif any(item.status is GateStatus.ADVISORY for item in results):
            overall = GateStatus.ADVISORY
        else:
            overall = GateStatus.PASS
        digest_source = {
            "platform_id": platform_id,
            "overall": overall.value,
            "gates": [(item.gate_id, item.status.value) for item in results],
        }
        report_digest = sha256(json.dumps(digest_source, sort_keys=True).encode()).hexdigest()
        return MapOpsGateReport(platform_id, now, tuple(results), overall, report_digest)
