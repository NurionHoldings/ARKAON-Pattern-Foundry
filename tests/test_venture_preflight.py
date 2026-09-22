import pytest
from apf.venture_preflight import EvidenceCandidate, RightsEnvelope, VentureIntent, VenturePreflightError, build_preflight

def intent():
    return VentureIntent(project_id="park-se-ri-character-ip", working_title="세리의 드림라운드",
        purpose="박세리의 개척 정신을 친근한 캐릭터와 참여형 콘텐츠로 확장한다.",
        audiences=["어린이와 가족", "골프 팬", "해외 K-컬처 이용자"], markets=["대한민국", "글로벌"],
        public_figure_inspired=True, public_figure_name="박세리")

def evidence(index: int, status: str = "VERIFIED"):
    return EvidenceCandidate(evidence_id=f"source-{index}", topic="스포츠 인물 IP 확장 사례",
        source_url=f"https://example.org/source/{index}", source_type="official_brand",
        jurisdiction="GLOBAL", retrieved_at="2026-09-22T00:00:00Z" if status == "VERIFIED" else None,
        claim=f"검증 범위가 제한된 사실 {index}" if status == "VERIFIED" else None,
        verification_status=status)

def cleared_rights():
    return RightsEnvelope(identity_license_verified=True, name_likeness_voice_scope=["name", "likeness"],
        trademark_clearance_verified=True, territory_and_term_defined=True, revenue_share_defined=True,
        evidence_digest="sha256:" + "a" * 64)

def test_public_figure_project_starts_research_only_without_rights_or_evidence():
    result = build_preflight(intent(), RightsEnvelope(), [])
    assert result.status == "RESEARCH_AND_PLANNING_ONLY"
    assert result.planning_allowed is True
    assert result.prototype_allowed is False
    assert result.commercial_use_allowed is False
    assert result.deployment_allowed is False
    assert "PUBLIC_FIGURE_RIGHTS_CLEARANCE" in result.unresolved_gates

def test_three_verified_sources_and_approvals_allow_only_controlled_prototype():
    result = build_preflight(intent(), RightsEnvelope(), [evidence(1), evidence(2), evidence(3)],
        specification_approved=True, sandbox_approved=True)
    assert result.status == "READY_FOR_CONTROLLED_PROTOTYPE"
    assert result.prototype_allowed is True
    assert result.commercial_use_allowed is False
    assert result.deployment_allowed is False

def test_verified_rights_never_imply_deployment_permission():
    result = build_preflight(intent(), cleared_rights(), [evidence(1), evidence(2), evidence(3)],
        specification_approved=True, sandbox_approved=True)
    assert result.status == "RIGHTS_CLEARED_SANDBOX_ONLY"
    assert result.commercial_use_allowed is True
    assert result.deployment_allowed is False

def test_duplicate_evidence_ids_fail_closed():
    with pytest.raises(VenturePreflightError, match="DUPLICATE"):
        build_preflight(intent(), RightsEnvelope(), [evidence(1), evidence(1)])

def test_verified_evidence_requires_bounded_claim_and_retrieval_time():
    with pytest.raises(ValueError):
        EvidenceCandidate(evidence_id="invalid-source", topic="사례",
            source_url="https://example.org/source", source_type="official_brand",
            jurisdiction="GLOBAL", verification_status="VERIFIED")

def test_preflight_has_all_required_disciplines():
    result = build_preflight(intent(), RightsEnvelope(), [])
    disciplines = {packet.discipline for packet in result.work_packets}
    assert {"검색", "분석", "기획", "구현", "운영", "권리·평판"} <= disciplines
    assert all(packet.required_outputs and packet.acceptance_checks for packet in result.work_packets)
