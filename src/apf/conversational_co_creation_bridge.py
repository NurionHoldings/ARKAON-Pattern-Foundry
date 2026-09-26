"""Bridge co-creation proposals into operator-decision inbox packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .central_orchestrator import InboxStage, OrchestratorError
from .conversational_co_creation import CoCreationPolicy, CoCreationProposal

SCHEMA_CO_CREATION_INBOX = "apf.conversational-co-creation-inbox/v1"


def build_co_creation_inbox_document(
    *,
    packet_id: str,
    proposal: CoCreationProposal,
    created_at: datetime,
) -> dict[str, object]:
    summary = (
        f"{proposal.platform_id}: conversational co-creation {proposal.scope.value} proposal "
        f"{proposal.proposal_id}; sections={', '.join(proposal.recommended_structure)}; "
        "operator review before template/platform build"
    )
    return {
        "schema_version": SCHEMA_CO_CREATION_INBOX,
        "packet_id": packet_id,
        "stage": InboxStage.OPERATOR_DECISION.value,
        "platform_id": proposal.platform_id,
        "packet_kind": "CONVERSATIONAL_CO_CREATION_PROPOSAL",
        "tenant_id": proposal.tenant_id,
        "principal_id": proposal.principal_id,
        "session_id": proposal.session_id,
        "proposal_id": proposal.proposal_id,
        "proposal_digest": proposal.proposal_digest,
        "scope": proposal.scope.value,
        "domain_brief": proposal.domain_brief,
        "recommended_structure": list(proposal.recommended_structure),
        "copy_angle_options": list(proposal.copy_angle_options),
        "evidence_table": [item.to_document() for item in proposal.evidence_table],
        "template_blueprint": [item.to_document() for item in proposal.template_blueprint],
        "platform_blueprint": [item.to_document() for item in proposal.platform_blueprint],
        "synthesis_test_plan": list(proposal.synthesis_test_plan),
        "assistant_reply": proposal.assistant_reply,
        "summary": summary,
        "automatic_implement_allowed": False,
        "production_change_allowed": False,
        "created_at": created_at.isoformat(),
    }


def write_co_creation_inbox_packet(*, foundry_root: Path, document: dict[str, object], dry_run: bool) -> str:
    if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
        raise OrchestratorError("INBOX_FORBIDDEN", "co-creation inbox packets must remain propose-only")
    target = foundry_root / "inbox" / "operator-decision" / f"{document['packet_id']}.json"
    if dry_run:
        return target.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target.as_posix()


def bridge_co_creation_proposal(
    *,
    foundry_root: Path,
    proposal: CoCreationProposal,
    policy: CoCreationPolicy,
    run_id: str,
    now: datetime,
    dry_run: bool,
) -> list[str]:
    if not policy.emit_operator_proposal:
        return []
    document = build_co_creation_inbox_document(
        packet_id=f"{run_id}-co-creation-{proposal.proposal_id}",
        proposal=proposal,
        created_at=now,
    )
    return [write_co_creation_inbox_packet(foundry_root=foundry_root, document=document, dry_run=dry_run)]
