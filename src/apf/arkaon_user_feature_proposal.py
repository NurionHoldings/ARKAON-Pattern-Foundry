"""Propose newly evolved ARKAON features to users based on improvement analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .arkaon_self_evolution_analysis import (
    AddedFeatureInsight,
    ArkaonSelfEvolutionAnalysisEngine,
    EvolutionImprovementAnalysis,
    SelfEvolutionAnalysisRejected,
)
from .conversational_co_creation import verify_payment_entitlement


class UserFeatureProposalRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class UserFeatureProposalPolicy:
    enabled: bool = True
    require_payment_entitlement: bool = True
    maximum_features_per_proposal: int = 5
    emit_operator_notice: bool = True

    @classmethod
    def load(cls, path: Path) -> UserFeatureProposalPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.user-feature-proposal/v1":
            raise UserFeatureProposalRejected("POLICY_SCHEMA", "unsupported user feature proposal schema")
        return cls(
            enabled=bool(document.get("enabled", True)),
            require_payment_entitlement=bool(document.get("require_payment_entitlement", True)),
            maximum_features_per_proposal=max(1, int(document.get("maximum_features_per_proposal", 5))),
            emit_operator_notice=bool(document.get("emit_operator_notice", True)),
        )


@dataclass(frozen=True)
class UserFeatureOffer:
    feature_id: str
    headline: str
    user_value: str
    suggested_prompt: str
    process_phase: str

    def to_document(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "headline": self.headline,
            "user_value": self.user_value,
            "suggested_prompt": self.suggested_prompt,
            "process_phase": self.process_phase,
        }


@dataclass(frozen=True)
class UserFeatureProposal:
    proposal_id: str
    tenant_id: str
    principal_id: str
    platform_id: str
    analysis_digest: str
    process_narrative: str
    assistant_pitch: str
    feature_offers: tuple[UserFeatureOffer, ...]
    co_creation_entry_hint: str
    proposal_digest: str
    created_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.user-feature-proposal/v1",
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "platform_id": self.platform_id,
            "analysis_digest": self.analysis_digest,
            "process_narrative": self.process_narrative,
            "assistant_pitch": self.assistant_pitch,
            "feature_offers": [item.to_document() for item in self.feature_offers],
            "co_creation_entry_hint": self.co_creation_entry_hint,
            "proposal_digest": self.proposal_digest,
            "review_status": "PROPOSED",
            "automatic_implement_allowed": False,
            "production_change_allowed": False,
            "created_at": self.created_at.isoformat(),
        }


def _build_assistant_pitch(
    *,
    analysis: EvolutionImprovementAnalysis,
    offers: tuple[UserFeatureOffer, ...],
) -> str:
    if not offers:
        return (
            "아르카온이 최근 개선되었습니다. "
            f"{analysis.process_narrative} "
            "Co-Creation 채팅으로 원하시는 작품 방향을 말씀해 주세요."
        )
    headlines = ", ".join(offer.headline for offer in offers[:3])
    return (
        f"아르카온이 나아졌습니다 — {headlines} 등 {len(offers)}가지 기능을 사용할 수 있습니다. "
        f"개선 과정: {analysis.process_narrative} "
        "아래 제안 프롬프트로 Co-Creation을 시작해 보세요."
    )


def _offers_from_insights(
    insights: tuple[AddedFeatureInsight, ...],
    *,
    maximum: int,
) -> tuple[UserFeatureOffer, ...]:
    proposable = [item for item in insights if item.proposable_to_user and item.suggested_prompt]
    if not proposable:
        proposable = [item for item in insights if item.proposable_to_user]
    selected = proposable[:maximum]
    return tuple(
        UserFeatureOffer(
            feature_id=item.feature_id,
            headline=item.headline,
            user_value=item.user_value,
            suggested_prompt=item.suggested_prompt,
            process_phase=item.process_phase,
        )
        for item in selected
    )


class ArkaonUserFeatureProposalEngine:
    def __init__(self, *, foundry_root: Path, policy: UserFeatureProposalPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-user-feature-proposal.json"
        self.policy = policy or UserFeatureProposalPolicy.load(config)
        self.analysis_engine = ArkaonSelfEvolutionAnalysisEngine(foundry_root=self.foundry_root)
        self.proposal_root = self.foundry_root / "state" / "self-evolution" / "user-proposals"
        self.proposal_root.mkdir(parents=True, exist_ok=True)

    def propose_from_analysis(
        self,
        *,
        analysis: EvolutionImprovementAnalysis,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        now: datetime,
    ) -> UserFeatureProposal:
        if now.tzinfo is None:
            raise UserFeatureProposalRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise UserFeatureProposalRejected("DISABLED", "user feature proposal is disabled")

        offers = _offers_from_insights(
            analysis.added_features,
            maximum=self.policy.maximum_features_per_proposal,
        )
        assistant_pitch = _build_assistant_pitch(analysis=analysis, offers=offers)
        co_creation_hint = (
            "POST /v1/console/co-creation/chat — feature_offers[].suggested_prompt 참고"
            if offers
            else "POST /v1/console/co-creation/chat"
        )
        proposal_id = sha256(
            f"{tenant_id}|{platform_id}|{analysis.analysis_digest}|{now.isoformat()}".encode()
        ).hexdigest()[:24]
        body = {
            "proposal_id": proposal_id,
            "tenant_id": tenant_id,
            "platform_id": platform_id,
            "analysis_digest": analysis.analysis_digest,
            "feature_ids": [item.feature_id for item in offers],
        }
        proposal_digest = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        proposal = UserFeatureProposal(
            proposal_id=proposal_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            analysis_digest=analysis.analysis_digest,
            process_narrative=analysis.process_narrative,
            assistant_pitch=assistant_pitch,
            feature_offers=offers,
            co_creation_entry_hint=co_creation_hint,
            proposal_digest=proposal_digest,
            created_at=now,
        )
        path = self.proposal_root / f"{proposal_id}.json"
        path.write_text(
            json.dumps(proposal.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if self.policy.emit_operator_notice:
            notice = {
                "schema_version": "apf.user-feature-proposal-notice/v1",
                "notice_id": str(uuid4()),
                "proposal_id": proposal_id,
                "platform_id": platform_id,
                "tenant_id": tenant_id,
                "summary": f"ARKAON evolved — {len(offers)} feature(s) proposed to user",
                "automatic_implement_allowed": False,
            }
            inbox = self.foundry_root / "inbox" / "operator-decision"
            inbox.mkdir(parents=True, exist_ok=True)
            (inbox / f"{proposal_id}-user-feature-proposal.json").write_text(
                json.dumps(notice, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return proposal

    def propose_to_user(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        payment_entitlement_digest: str,
        now: datetime,
        analysis_digest: str | None = None,
        baseline_snapshot_id: str | None = None,
        candidate_snapshot_id: str | None = None,
    ) -> UserFeatureProposal:
        if self.policy.require_payment_entitlement and not verify_payment_entitlement(
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            digest=payment_entitlement_digest,
            foundry_root=self.foundry_root,
        ):
            raise UserFeatureProposalRejected("ENTITLEMENT_INACTIVE", "valid payment entitlement required")

        if analysis_digest:
            analysis = self.analysis_engine.load_analysis(analysis_digest)
        elif baseline_snapshot_id and candidate_snapshot_id:
            analysis = self.analysis_engine.analyze(
                baseline_snapshot_id=baseline_snapshot_id,
                candidate_snapshot_id=candidate_snapshot_id,
                now=now,
            )
        else:
            try:
                analysis = self.analysis_engine.analyze_latest(now=now)
            except SelfEvolutionAnalysisRejected as error:
                raise UserFeatureProposalRejected(error.code, str(error)) from error

        return self.propose_from_analysis(
            analysis=analysis,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            now=now,
        )

    def list_proposals(
        self,
        *,
        tenant_id: str,
        limit: int = 20,
    ) -> tuple[UserFeatureProposal, ...]:
        paths = sorted(self.proposal_root.glob("*.json"), reverse=True)
        proposals: list[UserFeatureProposal] = []
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("tenant_id") != tenant_id:
                continue
            proposals.append(self._document_to_proposal(document))
            if len(proposals) >= limit:
                break
        return tuple(proposals)

    def _document_to_proposal(self, document: dict[str, object]) -> UserFeatureProposal:
        return UserFeatureProposal(
            proposal_id=str(document["proposal_id"]),
            tenant_id=str(document["tenant_id"]),
            principal_id=str(document["principal_id"]),
            platform_id=str(document["platform_id"]),
            analysis_digest=str(document["analysis_digest"]),
            process_narrative=str(document["process_narrative"]),
            assistant_pitch=str(document["assistant_pitch"]),
            feature_offers=tuple(
                UserFeatureOffer(
                    feature_id=str(item["feature_id"]),
                    headline=str(item["headline"]),
                    user_value=str(item["user_value"]),
                    suggested_prompt=str(item["suggested_prompt"]),
                    process_phase=str(item["process_phase"]),
                )
                for item in document.get("feature_offers") or []
            ),
            co_creation_entry_hint=str(document.get("co_creation_entry_hint", "")),
            proposal_digest=str(document["proposal_digest"]),
            created_at=datetime.fromisoformat(str(document["created_at"])),
        )
