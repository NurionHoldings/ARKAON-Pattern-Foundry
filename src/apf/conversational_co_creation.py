"""Conversational co-creation: paid in-platform chat → template/platform blueprint proposals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

_FORBIDDEN = re.compile(r"(password|credential|secret|pii|member|order|settlement)", re.IGNORECASE)


class CoCreationRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CoCreationScope(str, Enum):
    TEMPLATE = "TEMPLATE"
    PLATFORM = "PLATFORM"
    BOTH = "BOTH"


@dataclass(frozen=True)
class CoCreationPolicy:
    enabled: bool = True
    require_payment_entitlement: bool = True
    minimum_experience_artifacts: int = 1
    emit_operator_proposal: bool = True
    maximum_copy_angles: int = 3
    automatic_implement_allowed: bool = False
    production_change_allowed: bool = False

    @classmethod
    def load(cls, path: Path) -> CoCreationPolicy:
        if not path.is_file():
            return cls()
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != "apf.conversational-co-creation/v1":
            raise CoCreationRejected("POLICY_SCHEMA", "unsupported conversational co-creation schema")
        if document.get("automatic_implement_allowed") or document.get("production_change_allowed"):
            raise CoCreationRejected("POLICY_FORBIDDEN", "co-creation must remain propose-only")
        return cls(
            enabled=bool(document.get("enabled", True)),
            require_payment_entitlement=bool(document.get("require_payment_entitlement", True)),
            minimum_experience_artifacts=max(1, int(document.get("minimum_experience_artifacts", 1))),
            emit_operator_proposal=bool(document.get("emit_operator_proposal", True)),
            maximum_copy_angles=max(1, int(document.get("maximum_copy_angles", 3))),
            automatic_implement_allowed=bool(document.get("automatic_implement_allowed")),
            production_change_allowed=bool(document.get("production_change_allowed")),
        )


@dataclass(frozen=True)
class ChatTurn:
    role: str
    content: str
    recorded_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "role": self.role,
            "content": self.content,
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True)
class EvidenceRef:
    kind: str
    ref_id: str
    digest: str
    summary: str

    def to_document(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "ref_id": self.ref_id,
            "digest": self.digest,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class TemplateSectionBlueprint:
    section_id: str
    purpose: str
    pattern_token: str | None
    cta_slot: bool

    def to_document(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "purpose": self.purpose,
            "pattern_token": self.pattern_token,
            "cta_slot": self.cta_slot,
        }


@dataclass(frozen=True)
class PlatformSurfaceBlueprint:
    route_ref: str
    purpose: str

    def to_document(self) -> dict[str, object]:
        return {"route_ref": self.route_ref, "purpose": self.purpose}


@dataclass(frozen=True)
class CoCreationProposal:
    proposal_id: str
    session_id: str
    tenant_id: str
    principal_id: str
    platform_id: str
    scope: CoCreationScope
    domain_brief: str
    recommended_structure: tuple[str, ...]
    copy_angle_options: tuple[str, ...]
    evidence_table: tuple[EvidenceRef, ...]
    template_blueprint: tuple[TemplateSectionBlueprint, ...]
    platform_blueprint: tuple[PlatformSurfaceBlueprint, ...]
    synthesis_test_plan: tuple[str, ...]
    assistant_reply: str
    proposal_digest: str
    reference_site_url: str | None = None
    reference_style_path: str | None = None
    feature_reference_styles: tuple[dict[str, object], ...] = ()
    proposal_quality_score_at_intake: float | None = None
    proposal_quality_replenished: bool = False
    proposal_quality_replenish_trigger: str | None = None
    proposal_quality_replenish_digest: str | None = None

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-proposal/v1",
            "proposal_id": self.proposal_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "platform_id": self.platform_id,
            "scope": self.scope.value,
            "domain_brief": self.domain_brief,
            "recommended_structure": list(self.recommended_structure),
            "copy_angle_options": list(self.copy_angle_options),
            "evidence_table": [item.to_document() for item in self.evidence_table],
            "template_blueprint": [item.to_document() for item in self.template_blueprint],
            "platform_blueprint": [item.to_document() for item in self.platform_blueprint],
            "synthesis_test_plan": list(self.synthesis_test_plan),
            "assistant_reply": self.assistant_reply,
            "proposal_digest": self.proposal_digest,
            "reference_site_url": self.reference_site_url,
            "reference_style_path": self.reference_style_path,
            "feature_reference_styles": list(self.feature_reference_styles),
            "proposal_quality_score_at_intake": self.proposal_quality_score_at_intake,
            "proposal_quality_replenished": self.proposal_quality_replenished,
            "proposal_quality_replenish_trigger": self.proposal_quality_replenish_trigger,
            "proposal_quality_replenish_digest": self.proposal_quality_replenish_digest,
            "review_status": "PROPOSED",
            "automatic_implement_allowed": False,
            "production_change_allowed": False,
        }


@dataclass(frozen=True)
class CoCreationSession:
    session_id: str
    tenant_id: str
    principal_id: str
    platform_id: str
    scope: CoCreationScope
    turns: tuple[ChatTurn, ...]
    latest_proposal_id: str | None
    created_at: datetime
    updated_at: datetime

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": "apf.co-creation-session/v1",
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "platform_id": self.platform_id,
            "scope": self.scope.value,
            "turns": [item.to_document() for item in self.turns],
            "latest_proposal_id": self.latest_proposal_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


_KEYWORD_PATTERNS: tuple[tuple[str, str], ...] = (
    ("전자계약|e-contract|esign|계약서", "landing-pattern:e-contract-flow"),
    ("4단계|four-step|step process", "landing-pattern:four-step-process"),
    ("비교표|comparison", "landing-pattern:comparison-table"),
    ("마이페이지|dashboard|대시보드", "landing-pattern:mypage-dashboard"),
    ("hero|히어로|cta", "landing-pattern:hero-single-cta"),
    ("faq|자주", "landing-signal:faq_accordion"),
    ("환불|trust|신뢰", "landing-pattern:trust-refund-block"),
)


def verify_payment_entitlement(
    *,
    tenant_id: str,
    principal_id: str,
    platform_id: str,
    digest: str,
    foundry_root: Path | None = None,
) -> bool:
    if foundry_root is not None:
        from .billing_entitlement import BillingEntitlementVerifier

        return BillingEntitlementVerifier(foundry_root=foundry_root).verify(
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            payment_entitlement_digest=digest,
        )
    if len(digest) != 64 or not all(char in "0123456789abcdef" for char in digest):
        return False
    expected = sha256(f"{tenant_id}|{principal_id}|{platform_id}|paid".encode()).hexdigest()
    return digest == expected


def count_experience_artifacts(foundry_root: Path) -> int:
    from .proposal_quality_score import count_learning_artifacts

    return count_learning_artifacts(foundry_root)


def _scan_message_tokens(message: str) -> frozenset[str]:
    tokens: set[str] = set()
    for pattern, token in _KEYWORD_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            tokens.add(token)
    return frozenset(tokens)


def _load_landing_pattern_evidence(foundry_root: Path, tokens: frozenset[str]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    directory = foundry_root / "knowledge" / "landing-structure-patterns" / "proposed"
    if not directory.is_dir():
        return refs
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        token = str(document.get("pattern_token", ""))
        if tokens and token not in tokens:
            continue
        pattern_id = str(document.get("pattern_id", path.stem))
        digests = document.get("evidence_digests") or ()
        digest = str(digests[0]) if digests else sha256(path.read_bytes()).hexdigest()
        refs.append(
            EvidenceRef(
                kind="LANDING_STRUCTURE_PATTERN",
                ref_id=pattern_id,
                digest=digest,
                summary=str(document.get("summary", pattern_id)),
            )
        )
    return refs


def _default_copy_angles(tokens: frozenset[str], *, maximum: int) -> tuple[str, ...]:
    angle_map = {
        "landing-pattern:e-contract-flow": "esign-step-clarity",
        "landing-pattern:four-step-process": "process-clarity",
        "landing-pattern:comparison-table": "competitor-diff-matrix",
        "landing-pattern:mypage-dashboard": "post-contract-lifecycle",
        "landing-pattern:hero-single-cta": "instant-primary-action",
        "landing-pattern:trust-refund-block": "risk-reversal-trust",
    }
    angles = [angle_map[token] for token in sorted(tokens) if token in angle_map]
    if not angles:
        angles = ["evidence-before-cta", "numeric-benefit", "question-hook"]
    return tuple(angles[:maximum])


def _build_template_blueprint(tokens: frozenset[str]) -> tuple[TemplateSectionBlueprint, ...]:
    sections: list[TemplateSectionBlueprint] = []
    if "landing-pattern:hero-single-cta" in tokens or not tokens:
        sections.append(
            TemplateSectionBlueprint("hero", "primary value + single CTA", "landing-pattern:hero-single-cta", True)
        )
    if "landing-pattern:four-step-process" in tokens or "landing-pattern:e-contract-flow" in tokens:
        sections.append(
            TemplateSectionBlueprint(
                "process",
                "step funnel for contract or signup",
                "landing-pattern:four-step-process",
                False,
            )
        )
    if "landing-pattern:trust-refund-block" in tokens:
        sections.append(
            TemplateSectionBlueprint("trust", "risk reversal block", "landing-pattern:trust-refund-block", False)
        )
    if "landing-pattern:comparison-table" in tokens:
        sections.append(
            TemplateSectionBlueprint(
                "comparison",
                "differentiation matrix",
                "landing-pattern:comparison-table",
                False,
            )
        )
    if "landing-pattern:mypage-dashboard" in tokens:
        sections.append(
            TemplateSectionBlueprint(
                "lifecycle-preview",
                "post-conversion self-service preview",
                "landing-pattern:mypage-dashboard",
                False,
            )
        )
    if "landing-signal:faq_accordion" in tokens:
        sections.append(TemplateSectionBlueprint("faq", "objection handling", "landing-signal:faq_accordion", False))
    if not sections:
        sections.append(TemplateSectionBlueprint("hero", "default landing entry", None, True))
    return tuple(sections)


def _build_platform_blueprint(tokens: frozenset[str]) -> tuple[PlatformSurfaceBlueprint, ...]:
    surfaces: list[PlatformSurfaceBlueprint] = []
    if "landing-pattern:four-step-process" in tokens or "landing-pattern:e-contract-flow" in tokens:
        surfaces.extend(
            [
                PlatformSurfaceBlueprint("flow/step-select", "branch or plan selection"),
                PlatformSurfaceBlueprint("flow/step-info-payment", "identity and billing capture"),
                PlatformSurfaceBlueprint("flow/step-e-contract", "electronic contract signing"),
                PlatformSurfaceBlueprint("flow/step-complete", "confirmation and artifact delivery"),
            ]
        )
    if "landing-pattern:mypage-dashboard" in tokens:
        surfaces.append(PlatformSurfaceBlueprint("surface/mypage-dashboard", "self-service lifecycle hub"))
    if "landing-pattern:comparison-table" in tokens:
        surfaces.append(PlatformSurfaceBlueprint("surface/comparison-matrix", "public differentiation"))
    if not surfaces:
        surfaces.append(PlatformSurfaceBlueprint("surface/landing", "public acquisition surface"))
    return tuple(surfaces)


def _assistant_reply(*, scope: CoCreationScope, tokens: frozenset[str], evidence_count: int) -> str:
    focus = ", ".join(sorted(tokens)) if tokens else "general landing structure"
    scope_label = {
        CoCreationScope.TEMPLATE: "템플릿 구조",
        CoCreationScope.PLATFORM: "플랫폼 surface·flow",
        CoCreationScope.BOTH: "템플릿 + 플랫폼 blueprint",
    }[scope]
    return (
        f"요청을 {scope_label} 제안으로 정리했습니다. "
        f"근거-bound pattern {evidence_count}건과 정렬된 focus: {focus}. "
        "문구·디자인 원문 복제 없이 structural blueprint만 제안합니다. operator 승인 전 자동 배포는 없습니다."
    )


class ConversationalCoCreationEngine:
    def __init__(self, *, foundry_root: Path, policy: CoCreationPolicy | None = None) -> None:
        self.foundry_root = foundry_root.resolve()
        config = self.foundry_root / "config" / "arkaon-conversational-co-creation.json"
        self.policy = policy or CoCreationPolicy.load(config)
        self.session_root = self.foundry_root / "state" / "co-creation" / "sessions"
        self.proposal_root = self.foundry_root / "state" / "co-creation" / "proposals"
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.proposal_root.mkdir(parents=True, exist_ok=True)
        self._last_replenish_report = None

    def _load_session(self, session_id: str) -> CoCreationSession | None:
        path = self.session_root / f"{session_id}.json"
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        turns = tuple(
            ChatTurn(
                role=str(item["role"]),
                content=str(item["content"]),
                recorded_at=datetime.fromisoformat(str(item["recorded_at"])),
            )
            for item in document.get("turns") or ()
        )
        return CoCreationSession(
            session_id=str(document["session_id"]),
            tenant_id=str(document["tenant_id"]),
            principal_id=str(document["principal_id"]),
            platform_id=str(document["platform_id"]),
            scope=CoCreationScope(str(document.get("scope", CoCreationScope.BOTH.value))),
            turns=turns,
            latest_proposal_id=document.get("latest_proposal_id"),
            created_at=datetime.fromisoformat(str(document["created_at"])),
            updated_at=datetime.fromisoformat(str(document["updated_at"])),
        )

    def _save_session(self, session: CoCreationSession) -> None:
        path = self.session_root / f"{session.session_id}.json"
        path.write_text(
            json.dumps(session.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def chat(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        platform_id: str,
        message: str,
        scope: CoCreationScope,
        payment_entitlement_digest: str,
        now: datetime,
        session_id: str | None = None,
        reference_site_url: str | None = None,
        feature_reference_urls: dict[str, str] | None = None,
        fetch_payload=None,
    ) -> CoCreationProposal:
        if now.tzinfo is None:
            raise CoCreationRejected("TIMESTAMP", "timezone-aware timestamp required")
        if not self.policy.enabled:
            raise CoCreationRejected("DISABLED", "conversational co-creation is disabled")
        if _FORBIDDEN.search(message):
            raise CoCreationRejected("MESSAGE_FORBIDDEN", "message contains forbidden operational markers")
        if self.policy.require_payment_entitlement and not verify_payment_entitlement(
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            digest=payment_entitlement_digest,
            foundry_root=self.foundry_root,
        ):
            raise CoCreationRejected("PAYMENT_REQUIRED", "valid payment entitlement digest required")
        from .proposal_quality_replenish import resolve_proposal_quality_with_replenish
        from .proposal_quality_score import ProposalQualityRejected

        try:
            quality_report, replenish_report = resolve_proposal_quality_with_replenish(
                foundry_root=self.foundry_root,
                platform_id=platform_id,
                message=message,
                minimum_artifacts=self.policy.minimum_experience_artifacts,
                now=now,
            )
        except ProposalQualityRejected as error:
            raise CoCreationRejected(error.code, str(error)) from error
        proposal_quality_score = quality_report.score
        self._last_replenish_report = replenish_report
        session = self._load_session(session_id) if session_id else None
        if session is None:
            session_id = str(uuid4())
            session = CoCreationSession(
                session_id=session_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                platform_id=platform_id,
                scope=scope,
                turns=(),
                latest_proposal_id=None,
                created_at=now,
                updated_at=now,
            )
        elif session.tenant_id != tenant_id or session.principal_id != principal_id:
            raise CoCreationRejected("SESSION_FORBIDDEN", "session tenant/principal mismatch")

        user_turn = ChatTurn("user", message.strip(), now)
        tokens = _scan_message_tokens(message)
        if not tokens and session.turns:
            for prior in session.turns:
                if prior.role == "user":
                    tokens |= _scan_message_tokens(prior.content)
        evidence = _load_landing_pattern_evidence(self.foundry_root, tokens)
        template_blueprint = _build_template_blueprint(tokens) if scope in {
            CoCreationScope.TEMPLATE,
            CoCreationScope.BOTH,
        } else ()
        platform_blueprint = _build_platform_blueprint(tokens) if scope in {
            CoCreationScope.PLATFORM,
            CoCreationScope.BOTH,
        } else ()
        proposal_id = sha256(f"{session_id}|{now.isoformat()}|{message}".encode()).hexdigest()[:24]
        site_profile = None
        feature_profiles = ()
        reference_style_path = None
        if reference_site_url or feature_reference_urls:
            from .reference_url_style import (
                apply_reference_styles_to_sections,
                observe_feature_references,
                observe_reference_style,
                persist_reference_observations,
            )

            if reference_site_url:
                site_profile = observe_reference_style(
                    url=reference_site_url,
                    now=now,
                    fetch_payload=fetch_payload,
                )
                tokens |= frozenset(
                    f"ref-style:{tag}" for tag in site_profile.style_tags
                )
            if feature_reference_urls:
                feature_profiles = observe_feature_references(
                    feature_urls=feature_reference_urls,
                    now=now,
                    fetch_payload=fetch_payload,
                )
            if template_blueprint:
                template_blueprint = apply_reference_styles_to_sections(
                    template_blueprint,
                    site_profile=site_profile,
                    feature_profiles=feature_profiles,
                )
            reference_style_path = persist_reference_observations(
                foundry_root=self.foundry_root,
                tenant_id=tenant_id,
                proposal_id=proposal_id,
                site_profile=site_profile,
                feature_profiles=feature_profiles,
            )
        structure = tuple(section.section_id for section in template_blueprint) or ("landing",)
        copy_angles = _default_copy_angles(tokens, maximum=self.policy.maximum_copy_angles)
        domain_brief = (
            f"{platform_id} tenant co-creation: {message.strip()[:240]} "
            f"(scope={scope.value}; evidence-backed structural proposal only)"
        )
        digest_payload = {
            "proposal_id": proposal_id,
            "platform_id": platform_id,
            "scope": scope.value,
            "tokens": sorted(tokens),
            "evidence": [item.ref_id for item in evidence],
        }
        proposal_digest = sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
        assistant_reply = _assistant_reply(scope=scope, tokens=tokens, evidence_count=len(evidence))
        if reference_site_url:
            assistant_reply += (
                f" Reference site structural profile applied from {reference_site_url} "
                "(similar feel, no verbatim copy)."
            )
        if replenish_report is not None:
            assistant_reply += (
                f" Supplemental analysis added {len(replenish_report.actions)} learning asset(s) "
                f"(trigger={replenish_report.trigger}; score {replenish_report.before_score:.2f}"
                f"→{replenish_report.after_score:.2f}) before this re-proposal."
            )
        proposal = CoCreationProposal(
            proposal_id=proposal_id,
            session_id=session_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            platform_id=platform_id,
            scope=scope,
            domain_brief=domain_brief,
            recommended_structure=structure,
            copy_angle_options=copy_angles,
            evidence_table=tuple(evidence),
            template_blueprint=template_blueprint,
            platform_blueprint=platform_blueprint,
            synthesis_test_plan=(
                "shadow funnel walkthrough",
                "contamination gate for verbatim copy",
                "operator approval before build",
            ),
            assistant_reply=assistant_reply,
            proposal_digest=proposal_digest,
            reference_site_url=reference_site_url,
            reference_style_path=reference_style_path,
            feature_reference_styles=tuple(item.to_document() for item in feature_profiles),
            proposal_quality_score_at_intake=proposal_quality_score,
            proposal_quality_replenished=replenish_report is not None,
            proposal_quality_replenish_trigger=replenish_report.trigger if replenish_report else None,
            proposal_quality_replenish_digest=replenish_report.replenish_digest if replenish_report else None,
        )
        assistant_turn = ChatTurn("assistant", assistant_reply, now)
        updated_session = CoCreationSession(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            principal_id=session.principal_id,
            platform_id=session.platform_id,
            scope=scope,
            turns=session.turns + (user_turn, assistant_turn),
            latest_proposal_id=proposal_id,
            created_at=session.created_at,
            updated_at=now,
        )
        self._save_session(updated_session)
        proposal_path = self.proposal_root / f"{proposal_id}.json"
        proposal_path.write_text(
            json.dumps(proposal.to_document(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return proposal
