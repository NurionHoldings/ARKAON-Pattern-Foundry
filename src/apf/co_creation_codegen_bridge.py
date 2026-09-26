"""Bridge codegen manifests into operator-decision inbox packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .co_creation_codegen import CoCreationCodegenManifest, CoCreationCodegenPolicy

SCHEMA_CODEGEN_INBOX = "apf.co-creation-codegen-inbox/v1"


def build_codegen_inbox_document(
    *,
    packet_id: str,
    manifest: CoCreationCodegenManifest,
    created_at: datetime,
) -> dict[str, object]:
    summary = (
        f"{manifest.platform_id}: co-creation codegen {manifest.proposal_id}; "
        f"files={len(manifest.files)}; status={manifest.codegen_status}; "
        "operator review before preview sandbox"
    )
    return {
        "schema_version": SCHEMA_CODEGEN_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.OPERATOR_DECISION.value,
        "platform_id": manifest.platform_id,
        "packet_kind": "CO_CREATION_CODEGEN_REVIEW",
        "tenant_id": manifest.tenant_id,
        "proposal_id": manifest.proposal_id,
        "manifest_digest": manifest.manifest_digest,
        "output_root": manifest.output_root,
        "codegen_status": manifest.codegen_status,
        "files": [item.to_document() for item in manifest.files],
        "summary": summary,
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "created_at": created_at.isoformat(),
    }


def write_codegen_inbox_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise OrchestratorError("INBOX_FORBIDDEN", "codegen inbox packets must remain propose-only")
    target = foundry_root / "inbox" / "operator-decision" / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_codegen_manifest(
    *,
    foundry_root: Path,
    manifest: CoCreationCodegenManifest,
    policy: CoCreationCodegenPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> list[str]:
    if not policy.emit_operator_review_packet:
        return []
    document = build_codegen_inbox_document(
        packet_id=f"{run_id}-codegen-{manifest.proposal_id}",
        manifest=manifest,
        created_at=now,
    )
    return [write_codegen_inbox_packet(foundry_root=foundry_root, document=document, dry_run=dry_run)]
