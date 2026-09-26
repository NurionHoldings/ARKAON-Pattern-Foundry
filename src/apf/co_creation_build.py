"""Phase-3 scaffold: operator-approved template codegen and tenant preview sandbox."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path


class CoCreationBuildRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CoCreationBuildPolicy:
    enabled: bool = True
    require_operator_approval_digest: bool = True
    emit_preview_sandbox: bool = True
    emit_template_scaffold: bool = True
    automatic_deploy_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> CoCreationBuildPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.co-creation-build/v1":
            raise CoCreationBuildRejected("POLICY_SCHEMA", "unsupported co-creation build schema")
        if document.get("automatic_deploy_allowed"):
            raise CoCreationBuildRejected("POLICY_FORBIDDEN", "automatic deploy is not allowed")
        return cls(
            enabled=bool(document.get("enabled", True)),
            require_operator_approval_digest=bool(document.get("require_operator_approval_digest", True)),
            emit_preview_sandbox=bool(document.get("emit_preview_sandbox", True)),
            emit_template_scaffold=bool(document.get("emit_template_scaffold", True)),
            automatic_deploy_allowed=bool(document.get("automatic_deploy_allowed")),
        )


@dataclass(frozen=True)
class CoCreationBuildReport:
    proposal_id: str
    tenant_id: str
    platform_id: str
    preview_path: str
    scaffold_path: str
    build_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-build-report/v1",
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "platform_id": self.platform_id,
            "preview_path": self.preview_path,
            "scaffold_path": self.scaffold_path,
            "build_digest": self.build_digest,
            "automatic_deploy_allowed": False,
        }


class CoCreationBuildEngine:
    def __init__(self, *, foundry_root: Path, policy: CoCreationBuildPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-co-creation-build.json"
        self.policy = policy or CoCreationBuildPolicy.load(config)
        self.proposal_root = self.foundry_root / "state" / "co-creation" / "proposals"
        self.preview_root = self.foundry_root / "state" / "co-creation" / "previews"
        self.scaffold_root = self.foundry_root / "state" / "co-creation" / "scaffolds"

    def build_after_approval(
        self,
        *,
        proposal_id: str,
        operator_approval_digest: str,
        now: datetime,
    ) -> CoCreationBuildReport:
        if now.tzinfo is None:
            raise CoCreationBuildRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise CoCreationBuildRejected("DISABLED", "co-creation build is disabled")
        if self.policy.require_operator_approval_digest and len(operator_approval_digest) != 64:
            raise CoCreationBuildRejected("APPROVAL_REQUIRED", "operator approval digest required")
        proposal_path = self.proposal_root / f"{proposal_id}.json"
        if not proposal_path.is_file():
            raise CoCreationBuildRejected("PROPOSAL_NOT_FOUND", "proposal not found")
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        tenant_id = str(proposal.get("tenant_id", ""))
        platform_id = str(proposal.get("platform_id", ""))
        reference_bundle_path = self.foundry_root / "state" / "co-creation" / "reference-styles"
        reference_doc = None
        if reference_bundle_path.is_dir():
            for path in reference_bundle_path.glob(f"{proposal_id}-*.json"):
                reference_doc = json.loads(path.read_text(encoding="utf-8"))
                break
        preview = {
            "schema_version": "apf.co-creation-preview-sandbox/v1",
            "proposal_id": proposal_id,
            "tenant_id": tenant_id,
            "platform_id": platform_id,
            "operator_approval_digest": operator_approval_digest,
            "template_blueprint": proposal.get("template_blueprint") or [],
            "platform_blueprint": proposal.get("platform_blueprint") or [],
            "reference_style_bundle": reference_doc,
            "preview_mode": "TENANT_SANDBOX",
            "production_change_allowed": False,
            "created_at": now.isoformat(),
        }
        scaffold = {
            "schema_version": "apf.co-creation-template-scaffold/v1",
            "proposal_id": proposal_id,
            "platform_id": platform_id,
            "sections": [
                {
                    "section_id": item.get("section_id"),
                    "purpose": item.get("purpose"),
                    "pattern_token": item.get("pattern_token"),
                    "codegen_status": "PENDING_REVIEW",
                }
                for item in proposal.get("template_blueprint") or []
            ],
            "surfaces": proposal.get("platform_blueprint") or [],
            "reference_style_bundle": reference_doc,
            "notes": "structural scaffold only — no verbatim HTML/CSS from reference URLs",
        }
        build_digest = sha256(
            json.dumps({"proposal_id": proposal_id, "approval": operator_approval_digest}, sort_keys=True).encode()
        ).hexdigest()
        self.preview_root.mkdir(parents=True, exist_ok=True)
        self.scaffold_root.mkdir(parents=True, exist_ok=True)
        preview_path = self.preview_root / f"{proposal_id}-{build_digest[:12]}.json"
        scaffold_path = self.scaffold_root / f"{proposal_id}-{build_digest[:12]}.json"
        preview_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        scaffold_path.write_text(json.dumps(scaffold, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return CoCreationBuildReport(
            proposal_id=proposal_id,
            tenant_id=tenant_id,
            platform_id=platform_id,
            preview_path=preview_path.relative_to(self.foundry_root).as_posix(),
            scaffold_path=scaffold_path.relative_to(self.foundry_root).as_posix(),
            build_digest=build_digest,
        )
