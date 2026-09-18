"""Phase-4B: tenant-scoped preview sandbox for codegen variants."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from .co_creation_codegen import CoCreationCodegenEngine
from .conversational_co_creation import CoCreationRejected, CoCreationScope, ConversationalCoCreationEngine
from .conversational_co_creation import verify_payment_entitlement


class CoCreationPreviewRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PreviewSandboxStatus(str, Enum):
    PROVISION = "PROVISION"
    ACTIVE = "ACTIVE"
    FEEDBACK_LOOP = "FEEDBACK_LOOP"
    EXPIRED = "EXPIRED"
    PROMOTE_CANDIDATE = "PROMOTE_CANDIDATE"


@dataclass(frozen=True)
class CoCreationPreviewPolicy:
    enabled: bool = True
    preview_ttl_minutes: int = 120
    require_payment_entitlement: bool = True
    require_codegen_preview_ready: bool = True
    verify_entitlement_on_access: bool = True
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> CoCreationPreviewPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.co-creation-preview/v1":
            raise CoCreationPreviewRejected("POLICY_SCHEMA", "unsupported co-creation preview schema")
        if document.get("production_change_allowed"):
            raise CoCreationPreviewRejected("POLICY_FORBIDDEN", "preview must not allow production change")
        return cls(
            enabled=bool(document.get("enabled", True)),
            preview_ttl_minutes=max(5, int(document.get("preview_ttl_minutes", 120))),
            require_payment_entitlement=bool(document.get("require_payment_entitlement", True)),
            require_codegen_preview_ready=bool(document.get("require_codegen_preview_ready", True)),
            verify_entitlement_on_access=bool(document.get("verify_entitlement_on_access", True)),
            production_change_allowed=bool(document.get("production_change_allowed")),
        )


@dataclass(frozen=True)
class PreviewSandboxRuntime:
    sandbox_id: str
    proposal_id: str
    tenant_id: str
    principal_id: str
    platform_id: str
    status: PreviewSandboxStatus
    preview_url: str
    expires_at: datetime
    codegen_manifest_digest: str
    assets_root: str
    session_id: str | None
    latest_feedback_proposal_id: str | None
    created_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-preview-runtime/v1",
            "sandbox_id": self.sandbox_id,
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "platform_id": self.platform_id,
            "status": self.status.value,
            "preview_url": self.preview_url,
            "expires_at": self.expires_at.isoformat(),
            "codegen_manifest_digest": self.codegen_manifest_digest,
            "assets_root": self.assets_root,
            "session_id": self.session_id,
            "latest_feedback_proposal_id": self.latest_feedback_proposal_id,
            "preview_mode": "TENANT_SANDBOX",
            "production_change_allowed": False,
            "created_at": self.created_at.isoformat(),
        }


def _canonical_preview_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise CoCreationPreviewRejected("PREVIEW_URL_INSECURE", "preview base URL must be credential-free HTTPS")
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise CoCreationPreviewRejected("PREVIEW_URL_INSECURE", "preview base URL must not include path or query")
    return f"https://{parsed.hostname.lower()}{port}"


def _tenant_slug(tenant_id: str) -> str:
    return sha256(tenant_id.encode()).hexdigest()[:12]


def build_preview_url(*, preview_base_url: str, tenant_id: str, sandbox_id: str) -> str:
    base = _canonical_preview_base_url(preview_base_url)
    return f"{base}/t/{_tenant_slug(tenant_id)}/{sandbox_id}/"


def _verify_entitlement(
    *,
    foundry_root: Path,
    tenant_id: str,
    principal_id: str,
    platform_id: str,
    payment_entitlement_digest: str,
    policy: CoCreationPreviewPolicy,
) -> None:
    if not policy.require_payment_entitlement:
        return
    if not verify_payment_entitlement(
        tenant_id=tenant_id,
        principal_id=principal_id,
        platform_id=platform_id,
        digest=payment_entitlement_digest,
        foundry_root=foundry_root,
    ):
        raise CoCreationPreviewRejected("ENTITLEMENT_INACTIVE", "valid payment entitlement required")


class CoCreationPreviewEngine:
    def __init__(self, *, foundry_root: Path, policy: CoCreationPreviewPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-co-creation-preview.json"
        self.policy = policy or CoCreationPreviewPolicy.load(config)
        self.runtime_root = self.foundry_root / "state" / "co-creation" / "previews"
        self.codegen_engine = CoCreationCodegenEngine(foundry_root=self.foundry_root)
        self.proposal_root = self.foundry_root / "state" / "co-creation" / "proposals"

    def _runtime_path(self, sandbox_id: str) -> Path:
        return self.runtime_root / sandbox_id / "runtime.json"

    def _load_runtime_document(self, sandbox_id: str) -> dict[str, object]:
        path = self._runtime_path(sandbox_id)
        if not path.is_file():
            raise CoCreationPreviewRejected("SANDBOX_NOT_FOUND", "preview sandbox not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_runtime(self, runtime: PreviewSandboxRuntime) -> None:
        sandbox_dir = self.runtime_root / runtime.sandbox_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        path = sandbox_dir / "runtime.json"
        path.write_text(
            json.dumps(runtime.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _document_to_runtime(self, document: dict[str, object]) -> PreviewSandboxRuntime:
        return PreviewSandboxRuntime(
            sandbox_id=str(document["sandbox_id"]),
            proposal_id=str(document["proposal_id"]),
            tenant_id=str(document["tenant_id"]),
            principal_id=str(document["principal_id"]),
            platform_id=str(document["platform_id"]),
            status=PreviewSandboxStatus(str(document["status"])),
            preview_url=str(document["preview_url"]),
            expires_at=datetime.fromisoformat(str(document["expires_at"])),
            codegen_manifest_digest=str(document["codegen_manifest_digest"]),
            assets_root=str(document["assets_root"]),
            session_id=document.get("session_id") if document.get("session_id") else None,
            latest_feedback_proposal_id=(
                str(document["latest_feedback_proposal_id"])
                if document.get("latest_feedback_proposal_id")
                else None
            ),
            created_at=datetime.fromisoformat(str(document["created_at"])),
        )

    def _expire_if_needed(self, *, runtime: PreviewSandboxRuntime, now: datetime) -> PreviewSandboxRuntime:
        if runtime.status is PreviewSandboxStatus.EXPIRED:
            return runtime
        if now >= runtime.expires_at:
            expired = PreviewSandboxRuntime(
                sandbox_id=runtime.sandbox_id,
                proposal_id=runtime.proposal_id,
                tenant_id=runtime.tenant_id,
                principal_id=runtime.principal_id,
                platform_id=runtime.platform_id,
                status=PreviewSandboxStatus.EXPIRED,
                preview_url=runtime.preview_url,
                expires_at=runtime.expires_at,
                codegen_manifest_digest=runtime.codegen_manifest_digest,
                assets_root=runtime.assets_root,
                session_id=runtime.session_id,
                latest_feedback_proposal_id=runtime.latest_feedback_proposal_id,
                created_at=runtime.created_at,
            )
            self._save_runtime(expired)
            assets_dir = self.foundry_root / runtime.assets_root
            if assets_dir.is_dir():
                shutil.rmtree(assets_dir, ignore_errors=True)
            return expired
        return runtime

    def _assert_tenant_access(self, *, runtime: PreviewSandboxRuntime, tenant_id: str) -> None:
        if runtime.tenant_id != tenant_id:
            raise CoCreationPreviewRejected("TENANT_FORBIDDEN", "preview sandbox tenant mismatch")

    def _copy_codegen_assets(self, *, proposal_id: str, sandbox_id: str) -> str:
        source = self.foundry_root / "state" / "co-creation" / "codegen" / proposal_id
        if not source.is_dir():
            raise CoCreationPreviewRejected("CODEGEN_ASSETS_MISSING", "codegen output not found")
        assets_relative = f"state/co-creation/previews/{sandbox_id}/assets"
        target = self.foundry_root / assets_relative
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        for path in source.rglob("*"):
            if not path.is_file() or path.name == "manifest.json":
                continue
            relative = path.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        index_lines = [
            "<!DOCTYPE html>",
            "<html><head><title>ARKAON Preview Sandbox</title></head><body>",
            f"<!-- sandbox_id: {sandbox_id} -->",
            "<h1>Tenant Preview Sandbox</h1>",
            "<ul>",
        ]
        for section in sorted(target.glob("sections/*.html")):
            index_lines.append(f'<li><a href="{section.relative_to(target).as_posix()}">{section.name}</a></li>')
        index_lines.extend(["</ul>", "</body></html>"])
        (target / "index.html").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        return assets_relative

    def start_preview(
        self,
        *,
        proposal_id: str,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        preview_base_url: str,
        payment_entitlement_digest: str,
        now: datetime,
    ) -> PreviewSandboxRuntime:
        if now.tzinfo is None:
            raise CoCreationPreviewRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise CoCreationPreviewRejected("DISABLED", "co-creation preview is disabled")
        _verify_entitlement(
            foundry_root=self.foundry_root,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            payment_entitlement_digest=payment_entitlement_digest,
            policy=self.policy,
        )
        manifest = self.codegen_engine.load_manifest(proposal_id)
        if self.policy.require_codegen_preview_ready and manifest.codegen_status != "PREVIEW_READY":
            raise CoCreationPreviewRejected("CODEGEN_NOT_READY", "codegen must be PREVIEW_READY")
        if manifest.tenant_id != tenant_id:
            raise CoCreationPreviewRejected("TENANT_FORBIDDEN", "proposal tenant mismatch")
        if manifest.platform_id != platform_id:
            raise CoCreationPreviewRejected("PLATFORM_MISMATCH", "platform_id mismatch")

        proposal_path = self.proposal_root / f"{proposal_id}.json"
        session_id = None
        if proposal_path.is_file():
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            session_id = proposal.get("session_id")

        sandbox_id = sha256(f"{tenant_id}|{proposal_id}|{now.isoformat()}".encode()).hexdigest()[:16]
        preview_url = build_preview_url(
            preview_base_url=preview_base_url,
            tenant_id=tenant_id,
            sandbox_id=sandbox_id,
        )
        assets_root = self._copy_codegen_assets(proposal_id=proposal_id, sandbox_id=sandbox_id)
        expires_at = now + timedelta(minutes=self.policy.preview_ttl_minutes)
        runtime = PreviewSandboxRuntime(
            sandbox_id=sandbox_id,
            proposal_id=proposal_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            status=PreviewSandboxStatus.ACTIVE,
            preview_url=preview_url,
            expires_at=expires_at,
            codegen_manifest_digest=manifest.manifest_digest,
            assets_root=assets_root,
            session_id=str(session_id) if session_id else None,
            latest_feedback_proposal_id=None,
            created_at=now,
        )
        self._save_runtime(runtime)
        return runtime

    def get_sandbox(
        self,
        *,
        sandbox_id: str,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        payment_entitlement_digest: str | None,
        now: datetime,
    ) -> PreviewSandboxRuntime:
        if now.tzinfo is None:
            raise CoCreationPreviewRejected("TIMESTAMP", "timezone-aware timestamp required")
        document = self._load_runtime_document(sandbox_id)
        runtime = self._document_to_runtime(document)
        self._assert_tenant_access(runtime=runtime, tenant_id=tenant_id)
        runtime = self._expire_if_needed(runtime=runtime, now=now)
        if runtime.status is PreviewSandboxStatus.EXPIRED:
            raise CoCreationPreviewRejected("SANDBOX_EXPIRED", "preview sandbox expired")
        if self.policy.verify_entitlement_on_access:
            if not payment_entitlement_digest:
                raise CoCreationPreviewRejected("ENTITLEMENT_INACTIVE", "payment entitlement required for access")
            _verify_entitlement(
                foundry_root=self.foundry_root,
                tenant_id=tenant_id,
                principal_id=principal_id,
                platform_id=platform_id,
                payment_entitlement_digest=payment_entitlement_digest,
                policy=self.policy,
            )
        return runtime

    def teardown(
        self,
        *,
        sandbox_id: str,
        tenant_id: str,
        now: datetime,
    ) -> PreviewSandboxRuntime:
        if now.tzinfo is None:
            raise CoCreationPreviewRejected("TIMESTAMP", "timezone-aware timestamp required")
        document = self._load_runtime_document(sandbox_id)
        runtime = self._document_to_runtime(document)
        self._assert_tenant_access(runtime=runtime, tenant_id=tenant_id)
        expired = PreviewSandboxRuntime(
            sandbox_id=runtime.sandbox_id,
            proposal_id=runtime.proposal_id,
            tenant_id=runtime.tenant_id,
            principal_id=runtime.principal_id,
            platform_id=runtime.platform_id,
            status=PreviewSandboxStatus.EXPIRED,
            preview_url=runtime.preview_url,
            expires_at=now,
            codegen_manifest_digest=runtime.codegen_manifest_digest,
            assets_root=runtime.assets_root,
            session_id=runtime.session_id,
            latest_feedback_proposal_id=runtime.latest_feedback_proposal_id,
            created_at=runtime.created_at,
        )
        self._save_runtime(expired)
        assets_dir = self.foundry_root / runtime.assets_root
        if assets_dir.is_dir():
            shutil.rmtree(assets_dir, ignore_errors=True)
        return expired

    def submit_feedback(
        self,
        *,
        sandbox_id: str,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        message: str,
        payment_entitlement_digest: str,
        now: datetime,
    ) -> tuple[PreviewSandboxRuntime, str, dict[str, object]]:
        runtime = self.get_sandbox(
            sandbox_id=sandbox_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            payment_entitlement_digest=payment_entitlement_digest,
            now=now,
        )
        chat_engine = ConversationalCoCreationEngine(foundry_root=self.foundry_root)
        try:
            proposal = chat_engine.chat(
                tenant_id=tenant_id,
                principal_id=principal_id,
                platform_id=platform_id,
                message=message,
                scope=CoCreationScope.BOTH,
                payment_entitlement_digest=payment_entitlement_digest,
                now=now,
                session_id=runtime.session_id,
            )
        except CoCreationRejected as error:
            raise CoCreationPreviewRejected(error.code, error.args[0]) from error

        from .co_creation_feedback_loop import CoCreationFeedbackLoopEngine

        parent_proposal_id = runtime.latest_feedback_proposal_id or runtime.proposal_id
        loop_engine = CoCreationFeedbackLoopEngine(foundry_root=self.foundry_root)
        _diff, _state, loop_result = loop_engine.process_revision(
            parent_proposal_id=parent_proposal_id,
            revision=proposal,
            sandbox_id=sandbox_id,
            feedback_message=message,
            now=now,
        )
        replenish_report = getattr(chat_engine, "_last_replenish_report", None)
        if loop_result is not None and replenish_report is not None:
            loop_result = {
                **loop_result,
                "proposal_quality_replenish": replenish_report.to_document(),
            }

        updated = PreviewSandboxRuntime(
            sandbox_id=runtime.sandbox_id,
            proposal_id=runtime.proposal_id,
            tenant_id=runtime.tenant_id,
            principal_id=runtime.principal_id,
            platform_id=runtime.platform_id,
            status=PreviewSandboxStatus.FEEDBACK_LOOP,
            preview_url=runtime.preview_url,
            expires_at=runtime.expires_at,
            codegen_manifest_digest=runtime.codegen_manifest_digest,
            assets_root=runtime.assets_root,
            session_id=proposal.session_id,
            latest_feedback_proposal_id=proposal.proposal_id,
            created_at=runtime.created_at,
        )
        self._save_runtime(updated)
        return updated, proposal.proposal_id, loop_result or {}

    def accept_preview(
        self,
        *,
        sandbox_id: str,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        payment_entitlement_digest: str,
        now: datetime,
    ) -> PreviewSandboxRuntime:
        runtime = self.get_sandbox(
            sandbox_id=sandbox_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            payment_entitlement_digest=payment_entitlement_digest,
            now=now,
        )
        from .co_creation_deploy import CoCreationDeployEngine

        deploy_engine = CoCreationDeployEngine(foundry_root=self.foundry_root)
        deploy_engine.mark_promote_candidate(
            proposal_id=runtime.latest_feedback_proposal_id or runtime.proposal_id,
            sandbox_id=sandbox_id,
            now=now,
        )
        updated = PreviewSandboxRuntime(
            sandbox_id=runtime.sandbox_id,
            proposal_id=runtime.proposal_id,
            tenant_id=runtime.tenant_id,
            principal_id=runtime.principal_id,
            platform_id=runtime.platform_id,
            status=PreviewSandboxStatus.PROMOTE_CANDIDATE,
            preview_url=runtime.preview_url,
            expires_at=runtime.expires_at,
            codegen_manifest_digest=runtime.codegen_manifest_digest,
            assets_root=runtime.assets_root,
            session_id=runtime.session_id,
            latest_feedback_proposal_id=runtime.latest_feedback_proposal_id,
            created_at=runtime.created_at,
        )
        self._save_runtime(updated)
        return updated
