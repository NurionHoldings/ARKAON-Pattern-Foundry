"""Phase-4C/W4: staged co-creation deploy SHADOW → PILOT → PRODUCTION."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path

from .arkaon_self_evolution_compare import ArkaonSelfEvolutionCompareEngine, ImprovementContributor
from .predeployment_readiness import CheckStatus, PredeploymentReadinessHarness


class CoCreationDeployRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DeployRolloutStage(str, Enum):
    SHADOW = "SHADOW"
    PILOT = "PILOT"
    PRODUCTION = "PRODUCTION"
    PAUSED = "PAUSED"


@dataclass(frozen=True)
class CoCreationDeployPolicy:
    enabled: bool = True
    production_promotion_allowed: bool = False
    require_predeployment_pass: bool = True
    require_distinct_approvers: bool = True
    require_eternian_for_pilot: bool = True
    require_eternian_for_production: bool = True
    automatic_deploy_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> CoCreationDeployPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.co-creation-deploy/v1":
            raise CoCreationDeployRejected("POLICY_SCHEMA", "unsupported co-creation deploy schema")
        if document.get("automatic_deploy_allowed"):
            raise CoCreationDeployRejected("POLICY_FORBIDDEN", "automatic deploy is not allowed")
        return cls(
            enabled=bool(document.get("enabled", True)),
            production_promotion_allowed=bool(document.get("production_promotion_allowed", False)),
            require_predeployment_pass=bool(document.get("require_predeployment_pass", True)),
            require_distinct_approvers=bool(document.get("require_distinct_approvers", True)),
            require_eternian_for_pilot=bool(document.get("require_eternian_for_pilot", True)),
            require_eternian_for_production=bool(document.get("require_eternian_for_production", True)),
            automatic_deploy_allowed=bool(document.get("automatic_deploy_allowed")),
        )


@dataclass(frozen=True)
class DeployPromotionEvent:
    stage: DeployRolloutStage
    operator_approval_digest: str
    eternian_approval_digest: str | None
    operator_principal_id: str
    eternian_principal_id: str | None
    recorded_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "operator_approval_digest": self.operator_approval_digest,
            "eternian_approval_digest": self.eternian_approval_digest,
            "operator_principal_id": self.operator_principal_id,
            "eternian_principal_id": self.eternian_principal_id,
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True)
class CoCreationDeployState:
    proposal_id: str
    tenant_id: str
    platform_id: str
    sandbox_id: str | None
    current_stage: DeployRolloutStage
    codegen_manifest_digest: str
    promotion_log: tuple[DeployPromotionEvent, ...]
    rollback_digest: str | None
    deploy_digest: str
    production_change_allowed: bool

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-deploy-state/v1",
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "platform_id": self.platform_id,
            "sandbox_id": self.sandbox_id,
            "current_stage": self.current_stage.value,
            "codegen_manifest_digest": self.codegen_manifest_digest,
            "promotion_log": [item.to_document() for item in self.promotion_log],
            "rollback_digest": self.rollback_digest,
            "deploy_digest": self.deploy_digest,
            "production_change_allowed": False,
        }


_STAGE_ORDER = {
    DeployRolloutStage.SHADOW: 0,
    DeployRolloutStage.PILOT: 1,
    DeployRolloutStage.PRODUCTION: 2,
}


class CoCreationDeployEngine:
    def __init__(self, *, foundry_root: Path, policy: CoCreationDeployPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-co-creation-deploy.json"
        self.policy = policy or CoCreationDeployPolicy.load(config)
        self.deploy_root = self.foundry_root / "state" / "co-creation" / "deployments"
        self.deploy_root.mkdir(parents=True, exist_ok=True)

    def _deploy_dir(self, proposal_id: str) -> Path:
        return self.deploy_root / proposal_id

    def _state_path(self, proposal_id: str) -> Path:
        return self._deploy_dir(proposal_id) / "rollout.json"

    def _load_state(self, proposal_id: str) -> CoCreationDeployState:
        path = self._state_path(proposal_id)
        if not path.is_file():
            raise CoCreationDeployRejected("DEPLOY_NOT_FOUND", "deploy state not found")
        document = json.loads(path.read_text(encoding="utf-8"))
        promotion_log = tuple(
            DeployPromotionEvent(
                stage=DeployRolloutStage(str(item["stage"])),
                operator_approval_digest=str(item["operator_approval_digest"]),
                eternian_approval_digest=(
                    str(item["eternian_approval_digest"]) if item.get("eternian_approval_digest") else None
                ),
                operator_principal_id=str(item["operator_principal_id"]),
                eternian_principal_id=(
                    str(item["eternian_principal_id"]) if item.get("eternian_principal_id") else None
                ),
                recorded_at=datetime.fromisoformat(str(item["recorded_at"])),
            )
            for item in document.get("promotion_log") or []
        )
        return CoCreationDeployState(
            proposal_id=str(document["proposal_id"]),
            tenant_id=str(document["tenant_id"]),
            platform_id=str(document["platform_id"]),
            sandbox_id=document.get("sandbox_id"),
            current_stage=DeployRolloutStage(str(document["current_stage"])),
            codegen_manifest_digest=str(document["codegen_manifest_digest"]),
            promotion_log=promotion_log,
            rollback_digest=document.get("rollback_digest"),
            deploy_digest=str(document["deploy_digest"]),
            production_change_allowed=False,
        )

    def _save_state(self, state: CoCreationDeployState) -> None:
        deploy_dir = self._deploy_dir(state.proposal_id)
        deploy_dir.mkdir(parents=True, exist_ok=True)
        self._state_path(state.proposal_id).write_text(
            json.dumps(state.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _assert_predeployment(self, *, now: datetime) -> str:
        if not self.policy.require_predeployment_pass:
            return "skipped"
        store = self.foundry_root / "state" / "predeployment-readiness"
        if store.is_dir():
            reports = sorted(store.glob("*.json"), reverse=True)
            if reports:
                document = json.loads(reports[0].read_text(encoding="utf-8"))
                if document.get("overall") == CheckStatus.PASS.value:
                    return str(document.get("report_digest", ""))
        try:
            report = PredeploymentReadinessHarness(foundry_root=self.foundry_root).run(now=now)
            return report.report_digest
        except Exception as error:
            raise CoCreationDeployRejected("PREDEPLOY_FAILED", str(error)) from error

    def _assert_dual_approval(
        self,
        *,
        stage: DeployRolloutStage,
        operator_approval_digest: str,
        eternian_approval_digest: str | None,
        operator_principal_id: str,
        eternian_principal_id: str | None,
    ) -> None:
        if len(operator_approval_digest) != 64:
            raise CoCreationDeployRejected("APPROVAL_REQUIRED", "operator approval digest required")
        needs_eternian = (
            stage is DeployRolloutStage.PILOT and self.policy.require_eternian_for_pilot
        ) or (stage is DeployRolloutStage.PRODUCTION and self.policy.require_eternian_for_production)
        if needs_eternian:
            if not eternian_approval_digest or len(eternian_approval_digest) != 64:
                raise CoCreationDeployRejected("ETERNIAN_APPROVAL_REQUIRED", "eternian approval required")
            if not eternian_principal_id:
                raise CoCreationDeployRejected("ETERNIAN_APPROVAL_REQUIRED", "eternian principal required")
            if self.policy.require_distinct_approvers:
                if operator_approval_digest == eternian_approval_digest:
                    raise CoCreationDeployRejected("DUAL_APPROVAL_FORBIDDEN", "approvals must be distinct digests")
                if operator_principal_id == eternian_principal_id:
                    raise CoCreationDeployRejected("DUAL_APPROVAL_FORBIDDEN", "operator and eternian must differ")

    def start_shadow(
        self,
        *,
        proposal_id: str,
        tenant_id: str,
        platform_id: str,
        sandbox_id: str | None,
        codegen_manifest_digest: str,
        operator_approval_digest: str,
        operator_principal_id: str,
        now: datetime,
    ) -> CoCreationDeployState:
        if now.tzinfo is None:
            raise CoCreationDeployRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise CoCreationDeployRejected("DISABLED", "co-creation deploy is disabled")
        if self._state_path(proposal_id).is_file():
            raise CoCreationDeployRejected("DEPLOY_EXISTS", "deploy already started")
        self._assert_predeployment(now=now)
        if len(operator_approval_digest) != 64:
            raise CoCreationDeployRejected("APPROVAL_REQUIRED", "operator approval digest required")

        event = DeployPromotionEvent(
            stage=DeployRolloutStage.SHADOW,
            operator_approval_digest=operator_approval_digest,
            eternian_approval_digest=None,
            operator_principal_id=operator_principal_id,
            eternian_principal_id=None,
            recorded_at=now,
        )
        deploy_digest = sha256(
            json.dumps(
                {"proposal_id": proposal_id, "stage": "SHADOW", "codegen": codegen_manifest_digest},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        state = CoCreationDeployState(
            proposal_id=proposal_id,
            tenant_id=tenant_id,
            platform_id=platform_id,
            sandbox_id=sandbox_id,
            current_stage=DeployRolloutStage.SHADOW,
            codegen_manifest_digest=codegen_manifest_digest,
            promotion_log=(event,),
            rollback_digest=None,
            deploy_digest=deploy_digest,
            production_change_allowed=False,
        )
        self._save_state(state)
        rollback = {
            "schema_version": "apf.co-creation-deploy-rollback/v1",
            "proposal_id": proposal_id,
            "known_good_digest": deploy_digest,
            "recorded_at": now.isoformat(),
        }
        (self._deploy_dir(proposal_id) / "rollback.json").write_text(
            json.dumps(rollback, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        evolution = ArkaonSelfEvolutionCompareEngine(foundry_root=self.foundry_root)
        if evolution.policy.snapshot_on_deploy_stage:
            evolution.capture_snapshot(
                contributor=ImprovementContributor.BEOM,
                improvement_ref=proposal_id,
                improvement_summary="co-creation deploy SHADOW started",
                now=now,
            )
        return state

    def promote(
        self,
        *,
        proposal_id: str,
        stage: DeployRolloutStage,
        operator_approval_digest: str,
        eternian_approval_digest: str | None,
        operator_principal_id: str,
        eternian_principal_id: str | None,
        now: datetime,
    ) -> CoCreationDeployState:
        if now.tzinfo is None:
            raise CoCreationDeployRejected("TIMESTAMP", "timezone-aware timestamp required")
        if stage not in (DeployRolloutStage.PILOT, DeployRolloutStage.PRODUCTION):
            raise CoCreationDeployRejected("INVALID_STAGE", "promote target must be PILOT or PRODUCTION")
        if stage is DeployRolloutStage.PRODUCTION and not self.policy.production_promotion_allowed:
            raise CoCreationDeployRejected("PRODUCTION_LOCKED", "production promotion is locked")
        state = self._load_state(proposal_id)
        if state.current_stage is DeployRolloutStage.PAUSED:
            raise CoCreationDeployRejected("DEPLOY_PAUSED", "deploy is paused")
        expected_prior = DeployRolloutStage.SHADOW if stage is DeployRolloutStage.PILOT else DeployRolloutStage.PILOT
        if _STAGE_ORDER[state.current_stage] + 1 != _STAGE_ORDER[stage]:
            raise CoCreationDeployRejected("STAGE_ORDER", f"invalid promotion from {state.current_stage.value}")
        if state.current_stage != expected_prior:
            raise CoCreationDeployRejected("STAGE_ORDER", f"expected prior stage {expected_prior.value}")

        self._assert_predeployment(now=now)
        self._assert_dual_approval(
            stage=stage,
            operator_approval_digest=operator_approval_digest,
            eternian_approval_digest=eternian_approval_digest,
            operator_principal_id=operator_principal_id,
            eternian_principal_id=eternian_principal_id,
        )
        event = DeployPromotionEvent(
            stage=stage,
            operator_approval_digest=operator_approval_digest,
            eternian_approval_digest=eternian_approval_digest,
            operator_principal_id=operator_principal_id,
            eternian_principal_id=eternian_principal_id,
            recorded_at=now,
        )
        deploy_digest = sha256(
            json.dumps({"proposal_id": proposal_id, "stage": stage.value, "prior": state.deploy_digest}, sort_keys=True).encode()
        ).hexdigest()
        updated = CoCreationDeployState(
            proposal_id=state.proposal_id,
            tenant_id=state.tenant_id,
            platform_id=state.platform_id,
            sandbox_id=state.sandbox_id,
            current_stage=stage,
            codegen_manifest_digest=state.codegen_manifest_digest,
            promotion_log=(*state.promotion_log, event),
            rollback_digest=state.deploy_digest,
            deploy_digest=deploy_digest,
            production_change_allowed=False,
        )
        self._save_state(updated)
        evolution = ArkaonSelfEvolutionCompareEngine(foundry_root=self.foundry_root)
        if evolution.policy.snapshot_on_deploy_stage:
            contributor = ImprovementContributor.ETERNIAN if eternian_principal_id else ImprovementContributor.BEOM
            evolution.capture_snapshot(
                contributor=contributor,
                improvement_ref=proposal_id,
                improvement_summary=f"co-creation deploy promoted to {stage.value}",
                now=now,
            )
        return updated

    def kill_switch(
        self,
        *,
        proposal_id: str,
        operator_approval_digest: str,
        now: datetime,
    ) -> CoCreationDeployState:
        if now.tzinfo is None:
            raise CoCreationDeployRejected("TIMESTAMP", "timezone-aware timestamp required")
        if len(operator_approval_digest) != 64:
            raise CoCreationDeployRejected("APPROVAL_REQUIRED", "operator approval digest required")
        state = self._load_state(proposal_id)
        deploy_digest = sha256(
            json.dumps({"proposal_id": proposal_id, "kill": True, "prior": state.deploy_digest}, sort_keys=True).encode()
        ).hexdigest()
        updated = CoCreationDeployState(
            proposal_id=state.proposal_id,
            tenant_id=state.tenant_id,
            platform_id=state.platform_id,
            sandbox_id=state.sandbox_id,
            current_stage=DeployRolloutStage.PAUSED,
            codegen_manifest_digest=state.codegen_manifest_digest,
            promotion_log=state.promotion_log,
            rollback_digest=state.rollback_digest or state.deploy_digest,
            deploy_digest=deploy_digest,
            production_change_allowed=False,
        )
        self._save_state(updated)
        rollback_path = self._deploy_dir(proposal_id) / "rollback.json"
        rollback_path.write_text(
            json.dumps(
                {
                    "schema_version": "apf.co-creation-deploy-rollback/v1",
                    "proposal_id": proposal_id,
                    "known_good_digest": updated.rollback_digest,
                    "kill_switch_at": now.isoformat(),
                    "traffic_percent": 0,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return updated

    def get_status(self, proposal_id: str) -> CoCreationDeployState:
        return self._load_state(proposal_id)

    def mark_promote_candidate(
        self,
        *,
        proposal_id: str,
        sandbox_id: str,
        now: datetime,
    ) -> None:
        marker = {
            "schema_version": "apf.co-creation-promote-candidate/v1",
            "proposal_id": proposal_id,
            "sandbox_id": sandbox_id,
            "marked_at": now.isoformat(),
        }
        path = self._deploy_dir(proposal_id) / "promote-candidate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
