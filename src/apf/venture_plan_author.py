"""Supervised ARKAON drafting and Ethernian audit for venture plans."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field, model_validator


EvidenceState = Literal["MISSING", "PENDING", "VERIFIED"]
SectionState = Literal["DRAFT", "RESEARCH_REQUIRED", "READY_FOR_REVIEW"]


class Claim(BaseModel):
    text: str = Field(min_length=5, max_length=1000)
    kind: Literal["FACT", "INFERENCE", "HYPOTHESIS", "PROPOSAL"]
    evidence_state: EvidenceState = "MISSING"
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def verified_claim_requires_evidence(self) -> Claim:
        if self.evidence_state == "VERIFIED" and not self.evidence_ids:
            raise ValueError("verified claim requires evidence ids")
        return self


class PlanSectionInput(BaseModel):
    section_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    title: str = Field(min_length=3, max_length=160)
    category: list[str] = Field(min_length=1, max_length=10)
    objective: str = Field(min_length=10, max_length=1000)
    target_groups: list[str] = Field(min_length=1, max_length=20)
    core_design: list[str] = Field(min_length=1, max_length=30)
    partners_to_validate: list[str] = Field(default_factory=list, max_length=30)
    revenue_or_funding: list[str] = Field(default_factory=list, max_length=30)
    claims: list[Claim] = Field(default_factory=list, max_length=100)


class DraftedSection(BaseModel):
    section_id: str
    title: str
    state: SectionState
    objective: str
    target_groups: list[str]
    core_design: list[str]
    partners_to_validate: list[str]
    revenue_or_funding: list[str]
    required_evidence: list[str]
    decision_questions: list[str]
    risks: list[str]
    minimum_validation: str
    success_metrics: list[str]
    stop_condition: str


class VenturePlanDraft(BaseModel):
    schema_version: str = "apf.venture-plan-draft/1.0"
    project_id: str
    author: Literal["ARKAON"] = "ARKAON"
    status: Literal["SUPERVISED_DRAFT"] = "SUPERVISED_DRAFT"
    sections: list[DraftedSection]
    factual_claims: int
    verified_claims: int
    unsupported_factual_claims: int
    commercial_use_allowed: bool = False
    external_delivery_allowed: bool = False


class AuditFinding(BaseModel):
    section_id: str
    severity: Literal["BLOCKER", "MAJOR", "MINOR"]
    code: str
    finding: str
    required_action: str


class EthernianAudit(BaseModel):
    schema_version: str = "apf.venture-plan-audit/1.0"
    project_id: str
    reviewer: Literal["ETHERNIAN"] = "ETHERNIAN"
    verdict: Literal["HOLD", "CONDITIONAL_PASS", "PASS"]
    findings: list[AuditFinding]
    cross_project_actions: list[str]
    commercial_use_allowed: bool = False
    external_delivery_allowed: bool = False


def draft_section(item: PlanSectionInput) -> DraftedSection:
    fact_claims = [claim for claim in item.claims if claim.kind == "FACT"]
    unsupported = [claim for claim in fact_claims if claim.evidence_state != "VERIFIED"]
    required = [
        "수요와 이용자 문제를 확인할 공식통계·현장조사",
        "협력 후보의 참여의사와 법적 권한",
        "초기비용·운영비·재원·정산의 보수적 시나리오",
        "직접·간접 고용효과 산식과 기준시점",
        "성명·초상·상표·자료 사용 권리",
    ]
    if unsupported:
        required.insert(0, "미검증 사실 주장의 공식출처")
    state: SectionState = "RESEARCH_REQUIRED" if required else "DRAFT"
    return DraftedSection(
        section_id=item.section_id,
        title=item.title,
        state=state,
        objective=item.objective,
        target_groups=item.target_groups,
        core_design=item.core_design,
        partners_to_validate=item.partners_to_validate,
        revenue_or_funding=item.revenue_or_funding,
        required_evidence=required,
        decision_questions=[
            "박세리 감독이 이 사업에서 맡을 역할과 승인 범위는 무엇인가?",
            "첫 검증 지역·대상·상품을 어디까지 제한할 것인가?",
            "공익성과 수익성 중 1차 의사결정 기준의 우선순위는 무엇인가?",
        ],
        risks=[
            "실존 인물 권리와 브랜드 평판",
            "공공지원 확정 전 지원을 전제로 한 사업성 과대평가",
            "수요 검증 전 시설·인력·콘텐츠에 대한 선투자",
        ],
        minimum_validation="2개 이상 독립 근거와 이해관계자 인터뷰 후 저비용 시범 1건",
        success_metrics=[
            "핵심 대상의 참여·구매 의향",
            "시범사업 완료율과 재참여율",
            "단위경제성 또는 공공성과지표",
        ],
        stop_condition="권리 확보 실패, 핵심 협력주체 부재 또는 보수적 시나리오의 지속가능성 미달",
    )


def draft_plan(project_id: str, inputs: list[PlanSectionInput]) -> VenturePlanDraft:
    ids = [item.section_id for item in inputs]
    if len(ids) != len(set(ids)):
        raise ValueError("PLAN_SECTION_DUPLICATE")
    sections = [draft_section(item) for item in inputs]
    claims = [claim for item in inputs for claim in item.claims]
    facts = [claim for claim in claims if claim.kind == "FACT"]
    verified = [claim for claim in facts if claim.evidence_state == "VERIFIED"]
    return VenturePlanDraft(
        project_id=project_id,
        sections=sections,
        factual_claims=len(facts),
        verified_claims=len(verified),
        unsupported_factual_claims=len(facts) - len(verified),
    )


def audit_plan(draft: VenturePlanDraft) -> EthernianAudit:
    findings: list[AuditFinding] = []
    if draft.unsupported_factual_claims:
        findings.append(AuditFinding(
            section_id="portfolio", severity="BLOCKER", code="UNSUPPORTED_FACTS",
            finding=f"미검증 사실 주장 {draft.unsupported_factual_claims}건이 남아 있다.",
            required_action="공식·1차 출처를 연결하거나 가설·제안으로 재분류한다."))
    for section in draft.sections:
        checks = {
            "PARTNER_COMMITMENT_MISSING": (
                not section.partners_to_validate,
                "협력 주체 후보가 없다.",
                "권한과 참여의사를 검증할 기관·조직 후보를 지정한다."),
            "FUNDING_MODEL_MISSING": (
                not section.revenue_or_funding,
                "수익 또는 재원 가설이 없다.",
                "지불주체·비용주체·정산시점을 포함한 재원 가설을 작성한다."),
        }
        for code, (failed, finding, action) in checks.items():
            if failed:
                findings.append(AuditFinding(
                    section_id=section.section_id, severity="MAJOR", code=code,
                    finding=finding, required_action=action))
    counts = Counter(item.severity for item in findings)
    verdict: Literal["HOLD", "CONDITIONAL_PASS", "PASS"] = "PASS"
    if counts["BLOCKER"]:
        verdict = "HOLD"
    elif counts["MAJOR"]:
        verdict = "CONDITIONAL_PASS"
    return EthernianAudit(
        project_id=draft.project_id,
        verdict=verdict,
        findings=findings,
        cross_project_actions=[
            "8개 사업의 중복 기능·공통 조직·공통 데이터 자산을 매핑한다.",
            "골프장 건설은 별도 사전타당성·입지·환경·재무 모듈로 분리한다.",
            "국가 시책은 실제 공고·법정계획·예산을 확인한 뒤에만 특정 기관명을 사용한다.",
            "고용효과는 직접고용·간접고용·일시고용으로 나누고 기준시점을 고정한다.",
            "대외 제안본에는 확정·협의중·가설 상태를 시각적으로 구분한다.",
        ],
    )
