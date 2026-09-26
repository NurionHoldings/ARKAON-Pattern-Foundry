"""Phase-4A: operator-approved scaffold → structural variant codegen."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath

from .learning_safety import scan_learning_text

_ROUTE_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


class CoCreationCodegenRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CoCreationCodegenPolicy:
    enabled: bool = True
    require_operator_approval_digest: bool = True
    require_scaffold_manifest: bool = True
    emit_operator_review_packet: bool = True
    max_codegen_files: int = 64
    forbidden_relative_paths: tuple[str, ...] = (
        ".env",
        "secrets/",
        ".git/",
        "node_modules/",
    )
    automatic_deploy_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> CoCreationCodegenPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.co-creation-codegen/v1":
            raise CoCreationCodegenRejected("POLICY_SCHEMA", "unsupported co-creation codegen schema")
        if document.get("automatic_deploy_allowed"):
            raise CoCreationCodegenRejected("POLICY_FORBIDDEN", "automatic deploy is not allowed")
        return cls(
            enabled=bool(document.get("enabled", True)),
            require_operator_approval_digest=bool(document.get("require_operator_approval_digest", True)),
            require_scaffold_manifest=bool(document.get("require_scaffold_manifest", True)),
            emit_operator_review_packet=bool(document.get("emit_operator_review_packet", True)),
            max_codegen_files=max(1, int(document.get("max_codegen_files", 64))),
            forbidden_relative_paths=tuple(document.get("forbidden_relative_paths", cls.forbidden_relative_paths)),
            automatic_deploy_allowed=bool(document.get("automatic_deploy_allowed")),
        )


@dataclass(frozen=True)
class CodegenFileRecord:
    relative_path: str
    content_digest: str
    kind: str

    def to_document(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "content_digest": self.content_digest,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class CoCreationCodegenManifest:
    proposal_id: str
    tenant_id: str
    platform_id: str
    operator_approval_digest: str
    codegen_status: str
    files: tuple[CodegenFileRecord, ...]
    contamination_codes: tuple[str, ...]
    manifest_digest: str
    output_root: str
    created_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-codegen-manifest/v1",
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "platform_id": self.platform_id,
            "operator_approval_digest": self.operator_approval_digest,
            "codegen_status": self.codegen_status,
            "files": [item.to_document() for item in self.files],
            "contamination_codes": list(self.contamination_codes),
            "manifest_digest": self.manifest_digest,
            "output_root": self.output_root,
            "automatic_deploy_allowed": False,
            "production_change_allowed": False,
            "created_at": self.created_at.isoformat(),
        }


def _digest_content(content: str) -> str:
    return sha256(content.encode()).hexdigest()


def _sanitize_route_ref(route_ref: str) -> str:
    cleaned = _ROUTE_SAFE.sub("-", route_ref.strip("/")).strip("-")
    return cleaned or "root"


def _assert_safe_relative_path(*, relative_path: str, policy: CoCreationCodegenPolicy) -> None:
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise CoCreationCodegenRejected("FORBIDDEN_PATH", "relative path traversal is not allowed")
    joined = normalized.as_posix()
    for forbidden in policy.forbidden_relative_paths:
        if joined == forbidden.rstrip("/") or joined.startswith(forbidden):
            raise CoCreationCodegenRejected("FORBIDDEN_PATH", f"path forbidden: {relative_path}")


def _scan_text_fields(*values: str) -> tuple[str, ...]:
    codes: set[str] = set()
    for value in values:
        codes.update(scan_learning_text(value))
    return tuple(sorted(codes))


def _find_scaffold_path(scaffold_root: Path, proposal_id: str) -> Path | None:
    matches = sorted(scaffold_root.glob(f"{proposal_id}-*.json"), reverse=True)
    return matches[0] if matches else None


def _render_section_stub(*, section_id: str, purpose: str, pattern_token: str | None, style_tags: tuple[str, ...]) -> str:
    tags = ", ".join(style_tags) if style_tags else "neutral-rhythm"
    token = pattern_token or "landing-pattern:unspecified"
    return (
        "<!-- apf co-creation variant stub — structural only; no verbatim competitor copy -->\n"
        f'<section data-section-id="{section_id}" data-pattern-token="{token}">\n'
        f"  <!-- purpose: {purpose} -->\n"
        f"  <!-- reference feel tags: {tags} -->\n"
        "  <!-- copy-angle slot: evidence-bound angles only -->\n"
        "</section>\n"
    )


class CoCreationCodegenEngine:
    def __init__(self, *, foundry_root: Path, policy: CoCreationCodegenPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-co-creation-codegen.json"
        self.policy = policy or CoCreationCodegenPolicy.load(config)
        self.proposal_root = self.foundry_root / "state" / "co-creation" / "proposals"
        self.scaffold_root = self.foundry_root / "state" / "co-creation" / "scaffolds"
        self.codegen_root = self.foundry_root / "state" / "co-creation" / "codegen"

    def _load_proposal(self, proposal_id: str) -> dict[str, object]:
        proposal_path = self.proposal_root / f"{proposal_id}.json"
        if not proposal_path.is_file():
            raise CoCreationCodegenRejected("PROPOSAL_NOT_FOUND", "proposal not found")
        return json.loads(proposal_path.read_text(encoding="utf-8"))

    def _load_scaffold(self, proposal_id: str) -> dict[str, object]:
        if not self.policy.require_scaffold_manifest:
            return {}
        scaffold_path = _find_scaffold_path(self.scaffold_root, proposal_id)
        if scaffold_path is None:
            raise CoCreationCodegenRejected("SCAFFOLD_MISSING", "scaffold manifest not found")
        return json.loads(scaffold_path.read_text(encoding="utf-8"))

    def run_codegen(
        self,
        *,
        proposal_id: str,
        operator_approval_digest: str,
        now: datetime,
    ) -> CoCreationCodegenManifest:
        if now.tzinfo is None:
            raise CoCreationCodegenRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise CoCreationCodegenRejected("DISABLED", "co-creation codegen is disabled")
        if self.policy.require_operator_approval_digest and len(operator_approval_digest) != 64:
            raise CoCreationCodegenRejected("APPROVAL_REQUIRED", "operator approval digest required")

        proposal = self._load_proposal(proposal_id)
        review_status = str(proposal.get("review_status", "PROPOSED"))
        if review_status not in ("APPROVED", "PROPOSED"):
            raise CoCreationCodegenRejected("PROPOSAL_NOT_APPROVED", "proposal is not approved for codegen")

        scaffold = self._load_scaffold(proposal_id)
        sections = scaffold.get("sections") or proposal.get("template_blueprint") or []
        surfaces = scaffold.get("surfaces") or proposal.get("platform_blueprint") or []
        if not sections:
            raise CoCreationCodegenRejected("EVIDENCE_GAP", "template sections required for codegen")

        reference_bundle = scaffold.get("reference_style_bundle") or {}
        style_tags = tuple(reference_bundle.get("style_tags") or ())
        tenant_id = str(proposal.get("tenant_id", ""))
        platform_id = str(proposal.get("platform_id", ""))

        pending_files: list[tuple[str, str, str]] = []
        scan_values: list[str] = []

        for item in sections:
            if not isinstance(item, dict):
                continue
            section_id = str(item.get("section_id", ""))
            purpose = str(item.get("purpose", ""))
            pattern_token = item.get("pattern_token")
            if not section_id:
                raise CoCreationCodegenRejected("EVIDENCE_GAP", "section_id required")
            if not pattern_token:
                raise CoCreationCodegenRejected("EVIDENCE_GAP", f"pattern_token required for {section_id}")
            relative_path = f"sections/{section_id}.html"
            content = _render_section_stub(
                section_id=section_id,
                purpose=purpose,
                pattern_token=str(pattern_token),
                style_tags=style_tags,
            )
            pending_files.append((relative_path, content, "section_stub"))
            scan_values.extend([section_id, purpose, str(pattern_token), content])

        route_entries = []
        for item in surfaces:
            if not isinstance(item, dict):
                continue
            route_ref = str(item.get("route_ref", ""))
            purpose = str(item.get("purpose", ""))
            if not route_ref:
                continue
            safe_name = _sanitize_route_ref(route_ref)
            relative_path = f"surfaces/{safe_name}.route.json"
            payload = {
                "route_ref": route_ref,
                "purpose": purpose,
                "codegen_status": "GENERATED",
            }
            content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            pending_files.append((relative_path, content, "surface_route"))
            route_entries.append({"route_ref": route_ref, "purpose": purpose})
            scan_values.extend([route_ref, purpose, content])

        routes_payload = {
            "schema_version": "apf.co-creation-variant-routes/v1",
            "proposal_id": proposal_id,
            "platform_id": platform_id,
            "routes": route_entries,
        }
        routes_content = json.dumps(routes_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        pending_files.append(("routes.json", routes_content, "route_map"))
        scan_values.append(routes_content)

        readme = (
            "# Co-Creation Variant (structural stub)\n\n"
            f"- proposal_id: {proposal_id}\n"
            f"- platform_id: {platform_id}\n"
            "- verbatim HTML/CSS from reference URLs is forbidden\n"
            "- operator review required before preview sandbox\n"
        )
        pending_files.append(("README.md", readme, "readme"))
        scan_values.append(readme)

        contamination_codes = _scan_text_fields(*scan_values)
        if contamination_codes:
            raise CoCreationCodegenRejected(
                "CONTAMINATION_BLOCKED",
                "contamination scan blocked codegen: " + ",".join(contamination_codes),
            )

        if len(pending_files) > self.policy.max_codegen_files:
            raise CoCreationCodegenRejected("FILE_LIMIT", "codegen file count exceeds policy limit")

        output_dir = self.codegen_root / proposal_id
        output_dir.mkdir(parents=True, exist_ok=True)
        file_records: list[CodegenFileRecord] = []
        for relative_path, content, kind in pending_files:
            _assert_safe_relative_path(relative_path=relative_path, policy=self.policy)
            target = output_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            file_records.append(
                CodegenFileRecord(
                    relative_path=relative_path,
                    content_digest=_digest_content(content),
                    kind=kind,
                )
            )

        manifest_body = {
            "proposal_id": proposal_id,
            "tenant_id": tenant_id,
            "platform_id": platform_id,
            "operator_approval_digest": operator_approval_digest,
            "codegen_status": "GENERATED",
            "files": [item.to_document() for item in file_records],
            "contamination_codes": [],
        }
        manifest_digest = sha256(json.dumps(manifest_body, sort_keys=True).encode()).hexdigest()
        manifest = CoCreationCodegenManifest(
            proposal_id=proposal_id,
            tenant_id=tenant_id,
            platform_id=platform_id,
            operator_approval_digest=operator_approval_digest,
            codegen_status="GENERATED",
            files=tuple(file_records),
            contamination_codes=(),
            manifest_digest=manifest_digest,
            output_root=output_dir.relative_to(self.foundry_root).as_posix(),
            created_at=now,
        )
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        scaffold_path = _find_scaffold_path(self.scaffold_root, proposal_id)
        if scaffold_path is not None:
            scaffold_doc = json.loads(scaffold_path.read_text(encoding="utf-8"))
            updated_sections = []
            for item in scaffold_doc.get("sections") or []:
                if isinstance(item, dict):
                    updated = dict(item)
                    updated["codegen_status"] = "GENERATED"
                    updated_sections.append(updated)
            scaffold_doc["sections"] = updated_sections
            scaffold_doc["codegen_manifest_digest"] = manifest_digest
            scaffold_path.write_text(
                json.dumps(scaffold_doc, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )

        return manifest

    def load_manifest(self, proposal_id: str) -> CoCreationCodegenManifest:
        manifest_path = self.codegen_root / proposal_id / "manifest.json"
        if not manifest_path.is_file():
            raise CoCreationCodegenRejected("MANIFEST_NOT_FOUND", "codegen manifest not found")
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = tuple(
            CodegenFileRecord(
                relative_path=str(item["relative_path"]),
                content_digest=str(item["content_digest"]),
                kind=str(item["kind"]),
            )
            for item in document.get("files") or []
        )
        created_at = datetime.fromisoformat(str(document["created_at"]))
        return CoCreationCodegenManifest(
            proposal_id=str(document["proposal_id"]),
            tenant_id=str(document["tenant_id"]),
            platform_id=str(document["platform_id"]),
            operator_approval_digest=str(document["operator_approval_digest"]),
            codegen_status=str(document["codegen_status"]),
            files=files,
            contamination_codes=tuple(document.get("contamination_codes") or ()),
            manifest_digest=str(document["manifest_digest"]),
            output_root=str(document["output_root"]),
            created_at=created_at,
        )

    def approve_codegen(
        self,
        *,
        proposal_id: str,
        operator_codegen_approval_digest: str,
        now: datetime,
    ) -> CoCreationCodegenManifest:
        if now.tzinfo is None:
            raise CoCreationCodegenRejected("TIMESTAMP", "timezone-aware timestamp required")
        if len(operator_codegen_approval_digest) != 64:
            raise CoCreationCodegenRejected("APPROVAL_REQUIRED", "operator codegen approval digest required")
        manifest = self.load_manifest(proposal_id)
        if manifest.codegen_status not in ("GENERATED", "OPERATOR_APPROVED"):
            raise CoCreationCodegenRejected("INVALID_STATUS", "codegen must be GENERATED before approve")
        manifest_path = self.codegen_root / proposal_id / "manifest.json"
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        document["codegen_status"] = "PREVIEW_READY"
        document["operator_codegen_approval_digest"] = operator_codegen_approval_digest
        document["approved_at"] = now.isoformat()
        manifest_path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return self.load_manifest(proposal_id)
