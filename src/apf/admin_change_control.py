"""Governed admin change control: preview, partial-apply intent, rollback — never auto deploy."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path


class ChangeControlRejected(ValueError):
    pass


class ChangeProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    PREVIEWED = "PREVIEWED"
    ETERNIAN_REVIEWED = "ETERNIAN_REVIEWED"
    OPERATOR_APPROVED = "OPERATOR_APPROVED"
    PARTIALLY_APPLIED = "PARTIALLY_APPLIED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class AdminChangeControlPolicy:
    preview_required_before_apply: bool = True
    partial_apply_allowed: bool = True
    full_apply_requires_operator: bool = True
    automatic_merge_or_deploy: bool = False
    automatic_learning: bool = False
    production_change_allowed: bool = False
    rollback_token_required: bool = True
    forbidden_apply_categories: frozenset[str] = frozenset()

    @classmethod
    def load(cls, path: Path) -> AdminChangeControlPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.arkaon-admin-change-control/v1":
            raise ChangeControlRejected("unsupported admin change control schema")
        if (
            document.get("automatic_merge_or_deploy")
            or document.get("automatic_learning")
            or document.get("production_change_allowed")
        ):
            raise ChangeControlRejected("admin change control must remain propose-only")
        return cls(
            preview_required_before_apply=bool(document.get("preview_required_before_apply", True)),
            partial_apply_allowed=bool(document.get("partial_apply_allowed", True)),
            full_apply_requires_operator=bool(document.get("full_apply_requires_operator", True)),
            automatic_merge_or_deploy=bool(document.get("automatic_merge_or_deploy")),
            automatic_learning=bool(document.get("automatic_learning")),
            production_change_allowed=bool(document.get("production_change_allowed")),
            rollback_token_required=bool(document.get("rollback_token_required", True)),
            forbidden_apply_categories=frozenset(document.get("forbidden_apply_categories") or ()),
        )


@dataclass(frozen=True)
class ChangeScope:
    scope_id: str
    label: str
    preview_lines: tuple[str, ...]


@dataclass(frozen=True)
class ChangeProposal:
    proposal_id: str
    platform_id: str
    case_id: str | None
    source_digest: str
    summary: str
    scopes: tuple[ChangeScope, ...]
    status: ChangeProposalStatus
    created_at: datetime
    eternian_review_digest: str | None = None
    operator_decision_digest: str | None = None
    approved_scope_ids: tuple[str, ...] = ()
    rollback_token: str | None = None
    production_change_allowed: bool = False
    automatic_merge_or_deploy: bool = False

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.admin-change-proposal/v1",
            "proposal_id": self.proposal_id,
            "platform_id": self.platform_id,
            "case_id": self.case_id,
            "source_digest": self.source_digest,
            "summary": self.summary,
            "scopes": [
                {"scope_id": item.scope_id, "label": item.label, "preview_lines": list(item.preview_lines)}
                for item in self.scopes
            ],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "eternian_review_digest": self.eternian_review_digest,
            "operator_decision_digest": self.operator_decision_digest,
            "approved_scope_ids": list(self.approved_scope_ids),
            "rollback_token": self.rollback_token,
            "production_change_allowed": self.production_change_allowed,
            "automatic_merge_or_deploy": self.automatic_merge_or_deploy,
        }


@dataclass(frozen=True)
class ChangePreview:
    proposal_id: str
    preview_digest: str
    scope_previews: tuple[tuple[str, tuple[str, ...]], ...]
    preview_only: bool = True


@dataclass(frozen=True)
class PartialApplyRecord:
    proposal_id: str
    applied_scope_ids: tuple[str, ...]
    apply_digest: str
    rollback_token: str
    applied_at: datetime
    intent_only: bool = True


class AdminChangeController:
    """Records preview and partial-apply intent; never merges or deploys automatically."""

    def __init__(self, *, foundry_root: Path, policy: AdminChangeControlPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config_path = self.foundry_root / "config" / "arkaon-admin-change-control.json"
        self.policy = policy or AdminChangeControlPolicy.load(config_path)
        self.store_root = self.foundry_root / "state" / "change-control"
        self.store_root.mkdir(parents=True, exist_ok=True)
        self._proposals: dict[str, ChangeProposal] = {}
        self._apply_records: dict[str, PartialApplyRecord] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        for path in sorted(self.store_root.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("schema_version") != "apf.admin-change-proposal/v1":
                continue
            scopes = tuple(
                ChangeScope(
                    scope_id=str(item["scope_id"]),
                    label=str(item["label"]),
                    preview_lines=tuple(item.get("preview_lines") or ()),
                )
                for item in document.get("scopes") or ()
            )
            proposal = ChangeProposal(
                proposal_id=str(document["proposal_id"]),
                platform_id=str(document["platform_id"]),
                case_id=document.get("case_id"),
                source_digest=str(document["source_digest"]),
                summary=str(document["summary"]),
                scopes=scopes,
                status=ChangeProposalStatus(str(document["status"])),
                created_at=datetime.fromisoformat(str(document["created_at"])),
                eternian_review_digest=document.get("eternian_review_digest"),
                operator_decision_digest=document.get("operator_decision_digest"),
                approved_scope_ids=tuple(document.get("approved_scope_ids") or ()),
                rollback_token=document.get("rollback_token"),
            )
            self._proposals[proposal.proposal_id] = proposal

    def create_proposal(
        self,
        *,
        proposal_id: str,
        platform_id: str,
        source_digest: str,
        summary: str,
        scopes: tuple[ChangeScope, ...],
        now: datetime,
        case_id: str | None = None,
    ) -> ChangeProposal:
        if proposal_id in self._proposals:
            raise ChangeControlRejected("change proposal already exists")
        if not self._digest_ok(source_digest):
            raise ChangeControlRejected("source digest required")
        if not scopes:
            raise ChangeControlRejected("at least one change scope required")
        if now.tzinfo is None:
            raise ChangeControlRejected("timezone-aware timestamp required")
        self._scan_forbidden(summary)
        for scope in scopes:
            self._scan_forbidden(scope.label)
            for line in scope.preview_lines:
                self._scan_forbidden(line)
        proposal = ChangeProposal(
            proposal_id=proposal_id,
            platform_id=platform_id,
            case_id=case_id,
            source_digest=source_digest,
            summary=summary,
            scopes=scopes,
            status=ChangeProposalStatus.DRAFT,
            created_at=now,
        )
        return self._persist(proposal)

    def preview(self, proposal_id: str) -> ChangePreview:
        proposal = self._require(proposal_id)
        scope_previews = tuple((scope.scope_id, scope.preview_lines) for scope in proposal.scopes)
        preview_digest = self._digest(
            (proposal_id, proposal.source_digest, scope_previews, True)
        )
        updated = replace(proposal, status=ChangeProposalStatus.PREVIEWED)
        self._persist(updated)
        return ChangePreview(proposal_id, preview_digest, scope_previews, preview_only=True)

    def record_eternian_review(self, proposal_id: str, *, review_digest: str) -> ChangeProposal:
        proposal = self._require(proposal_id)
        if proposal.status not in (ChangeProposalStatus.DRAFT, ChangeProposalStatus.PREVIEWED):
            raise ChangeControlRejected("eternian review requires draft or previewed proposal")
        if self.policy.preview_required_before_apply and proposal.status is ChangeProposalStatus.DRAFT:
            raise ChangeControlRejected("preview required before eternian review")
        if not self._digest_ok(review_digest):
            raise ChangeControlRejected("eternian review digest required")
        updated = replace(
            proposal,
            eternian_review_digest=review_digest,
            status=ChangeProposalStatus.ETERNIAN_REVIEWED,
        )
        return self._persist(updated)

    def operator_approve(
        self,
        proposal_id: str,
        *,
        scope_ids: tuple[str, ...],
        decision_digest: str,
    ) -> ChangeProposal:
        proposal = self._require(proposal_id)
        if proposal.status is not ChangeProposalStatus.ETERNIAN_REVIEWED:
            raise ChangeControlRejected("operator approval requires eternian review first")
        if not self._digest_ok(decision_digest):
            raise ChangeControlRejected("operator decision digest required")
        if not scope_ids:
            raise ChangeControlRejected("at least one approved scope required")
        known = {scope.scope_id for scope in proposal.scopes}
        if not set(scope_ids).issubset(known):
            raise ChangeControlRejected("unknown scope in operator approval")
        if not self.policy.partial_apply_allowed and len(scope_ids) != len(proposal.scopes):
            raise ChangeControlRejected("partial apply is disabled by policy")
        updated = replace(
            proposal,
            operator_decision_digest=decision_digest,
            approved_scope_ids=scope_ids,
            status=ChangeProposalStatus.OPERATOR_APPROVED,
        )
        return self._persist(updated)

    def apply_partial(self, proposal_id: str, *, now: datetime) -> PartialApplyRecord:
        proposal = self._require(proposal_id)
        if proposal.status is not ChangeProposalStatus.OPERATOR_APPROVED:
            raise ChangeControlRejected("partial apply requires operator approval")
        if not proposal.approved_scope_ids:
            raise ChangeControlRejected("no approved scopes to apply")
        if now.tzinfo is None:
            raise ChangeControlRejected("timezone-aware timestamp required")
        rollback_token = secrets.token_hex(32)
        apply_digest = self._digest(
            (proposal_id, proposal.approved_scope_ids, proposal.operator_decision_digest, now.isoformat())
        )
        record = PartialApplyRecord(
            proposal_id=proposal_id,
            applied_scope_ids=proposal.approved_scope_ids,
            apply_digest=apply_digest,
            rollback_token=rollback_token,
            applied_at=now,
            intent_only=True,
        )
        updated = replace(
            proposal,
            status=ChangeProposalStatus.PARTIALLY_APPLIED,
            rollback_token=rollback_token,
        )
        self._persist(updated)
        self._apply_records[rollback_token] = record
        return record

    def rollback(self, rollback_token: str) -> ChangeProposal:
        record = self._apply_records.get(rollback_token)
        if record is None:
            raise ChangeControlRejected("rollback token not found")
        proposal = self._require(record.proposal_id)
        if proposal.rollback_token != rollback_token:
            raise ChangeControlRejected("rollback token mismatch")
        updated = replace(
            proposal,
            status=ChangeProposalStatus.ROLLED_BACK,
            rollback_token=None,
            approved_scope_ids=(),
        )
        del self._apply_records[rollback_token]
        return self._persist(updated)

    def get_proposal(self, proposal_id: str) -> ChangeProposal:
        return self._require(proposal_id)

    def list_proposals(self) -> tuple[ChangeProposal, ...]:
        return tuple(self._proposals.values())

    def auto_merge_or_deploy(self) -> None:
        raise ChangeControlRejected("automatic merge or deploy is forbidden")

    def apply_without_approval(self) -> None:
        raise ChangeControlRejected("apply without operator approval is forbidden")

    def _require(self, proposal_id: str) -> ChangeProposal:
        if proposal_id not in self._proposals:
            raise ChangeControlRejected("change proposal not found")
        return self._proposals[proposal_id]

    def _persist(self, proposal: ChangeProposal) -> ChangeProposal:
        self._proposals[proposal.proposal_id] = proposal
        target = self.store_root / f"{proposal.proposal_id}.json"
        target.write_text(
            json.dumps(proposal.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return proposal

    def _scan_forbidden(self, text: str) -> None:
        lowered = text.casefold()
        for token in self.policy.forbidden_apply_categories:
            if token.casefold() in lowered:
                raise ChangeControlRejected("operational or identity data cannot enter change control")

    @staticmethod
    def _digest(value: object) -> str:
        return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _digest_ok(value: str) -> bool:
        return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
