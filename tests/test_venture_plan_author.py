import pytest

from apf.venture_plan_author import (
    Claim,
    PlanSectionInput,
    audit_plan,
    draft_plan,
)


def section(**overrides):
    values = {
        "section_id": "symbolic-golf-course",
        "title": "박세리 상징 골프장",
        "category": ["공공협력", "산업"],
        "objective": "지역경제와 골프 교육을 연결하는 상징 거점을 검토한다.",
        "target_groups": ["지역주민", "골프관광객"],
        "core_design": ["골프장", "교육", "관광의 복합 검토"],
        "partners_to_validate": ["후보 지자체", "민간 투자자"],
        "revenue_or_funding": ["민간투자", "운영수익", "검증된 공공지원"],
        "claims": [],
    }
    values.update(overrides)
    return PlanSectionInput.model_validate(values)


def test_arkaon_draft_never_allows_commercial_use_or_external_delivery():
    draft = draft_plan("park-se-ri-character-ip", [section()])
    assert draft.author == "ARKAON"
    assert draft.status == "SUPERVISED_DRAFT"
    assert draft.commercial_use_allowed is False
    assert draft.external_delivery_allowed is False


def test_unverified_fact_becomes_audit_blocker():
    draft = draft_plan(
        "park-se-ri-character-ip",
        [section(claims=[Claim(text="후보 지자체가 사업을 지원한다.", kind="FACT")])],
    )
    audit = audit_plan(draft)
    assert draft.unsupported_factual_claims == 1
    assert audit.verdict == "HOLD"
    assert any(item.code == "UNSUPPORTED_FACTS" for item in audit.findings)


def test_verified_fact_requires_evidence_id():
    with pytest.raises(ValueError, match="evidence ids"):
        Claim(
            text="공식 문서에서 확인한 제한된 사실",
            kind="FACT",
            evidence_state="VERIFIED",
        )


def test_missing_partner_and_funding_are_separate_major_findings():
    draft = draft_plan(
        "park-se-ri-character-ip",
        [section(partners_to_validate=[], revenue_or_funding=[])],
    )
    audit = audit_plan(draft)
    codes = {item.code for item in audit.findings}
    assert {"PARTNER_COMMITMENT_MISSING", "FUNDING_MODEL_MISSING"} <= codes
    assert audit.verdict == "CONDITIONAL_PASS"


def test_duplicate_sections_fail_closed():
    with pytest.raises(ValueError, match="DUPLICATE"):
        draft_plan("park-se-ri-character-ip", [section(), section()])


def test_draft_requires_evidence_decisions_metrics_and_stop_condition():
    draft = draft_plan("park-se-ri-character-ip", [section()])
    item = draft.sections[0]
    assert item.required_evidence
    assert item.decision_questions
    assert item.success_metrics
    assert item.stop_condition
