import json
from pathlib import Path

import pytest

from apf.platform_launch_intelligence import (
    LaunchAnswer,
    LaunchFlow,
    LaunchIntelligenceError,
    LaunchIntent,
    OfficialFlowObservation,
    SingleSourceAssetException,
    abstract_patterns,
    build_blueprint,
    load_observations,
    next_questions,
)

ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "knowledge/platform-launch/official-flow-observations-v1.json"


def test_official_evidence_is_diverse_clean_room_and_https():
    observations = load_observations(EVIDENCE)
    assert len({item.provider for item in observations}) == 4
    assert all(item.official_url.startswith("https://") for item in observations)
    assert all(not item.copied_code and not item.copied_visual_design for item in observations)
    patterns = abstract_patterns(observations)
    assert patterns["prompt_to_draft"] == ("Bubble", "Framer", "Webflow", "Wix")
    assert "data_model_generation" not in patterns  # one provider is not a reusable pattern


def single_source_exception(**overrides):
    values = {
        "source_id": "bubble-mobile-ai-20260919",
        "capability": "data_model_generation",
        "rights_review": "PASS",
        "owner_approval_digest": "sha256:" + "a" * 64,
        "independent_implementation": True,
        "original_expression_excluded": True,
        "distinctive_additions": [
            {"category": "motion_interaction", "description": "상태 변화가 보이는 고유 텍스트 모션"},
            {"category": "workflow", "description": "권한별 시각적 승인과 되돌리기 흐름"},
        ],
        "similarity_review": "PASS",
        "approval_scope": "일반 기능 원리만 독립 구현하며 원본 표현과 화면 구성은 사용하지 않는다.",
    }
    values.update(overrides)
    return SingleSourceAssetException.model_validate(values)


def test_owner_approved_distinctive_clean_room_exception_can_promote_single_source_idea():
    patterns = abstract_patterns(
        load_observations(EVIDENCE), exceptions=[single_source_exception()]
    )
    assert patterns["data_model_generation"] == ("Bubble",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rights_review", "HOLD"),
        ("owner_approval_digest", "missing"),
        ("independent_implementation", False),
        ("original_expression_excluded", False),
        (
            "distinctive_additions",
            [{"category": "visual_identity", "description": "고유 색상 체계 한 가지만 변경"}],
        ),
        ("similarity_review", "HOLD"),
    ],
)
def test_single_source_exception_fails_closed_without_every_control(field, value):
    with pytest.raises(ValueError):
        single_source_exception(**{field: value})


def test_single_source_exception_must_match_recorded_source_capability():
    with pytest.raises(LaunchIntelligenceError, match="EVIDENCE_MISMATCH"):
        abstract_patterns(
            load_observations(EVIDENCE),
            exceptions=[single_source_exception(capability="unobserved_feature")],
        )


def test_cosmetic_only_color_and_animation_do_not_pass_without_functional_distinction():
    with pytest.raises(ValueError, match="functional distinction"):
        single_source_exception(
            distinctive_additions=[
                {"category": "visual_identity", "description": "브랜드 고유 색상 토큰과 대비 체계"},
                {"category": "motion_interaction", "description": "제목 텍스트의 고유 전환 애니메이션"},
            ]
        )


def test_copied_material_is_rejected():
    item = json.loads(EVIDENCE.read_text(encoding="utf-8"))["observations"][0]
    item["copied_marketing_copy"] = True
    with pytest.raises(ValueError, match="copied implementation material"):
        OfficialFlowObservation.model_validate(item)


def test_source_diversity_is_required(tmp_path):
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    document["observations"] = document["observations"][:2]
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(LaunchIntelligenceError, match="DIVERSITY"):
        load_observations(path)


def test_minimum_questions_expand_only_for_applicable_risk():
    intent = LaunchIntent(
        name="동네 장터", purpose="이웃이 물건을 나누는 공간",
        audience=["지역 주민"], core_action="물건 등록과 신청",
        collects_personal_data=True, needs_roles_or_permissions=False, needs_payment=False,
    )
    questions = next_questions(intent)
    assert [item["question_id"] for item in questions] == ["data_detail"]
    assert next_questions(intent, [LaunchAnswer(question_id="data_detail", answer="연락처")]) == []


def test_blueprint_connects_to_visual_brief_but_never_authorizes_changes():
    observations = load_observations(EVIDENCE)
    intent = LaunchIntent(
        name="예약 도우미", purpose="소규모 가게 예약을 간단히 받는다",
        audience=["가게 고객"], core_action="예약 시간 선택",
        collects_personal_data=False, needs_roles_or_permissions=False, needs_payment=False,
    )
    blueprint = build_blueprint(intent, observations)
    assert blueprint.next_step == "GENERATE_VISUAL_OPTIONS"
    assert blueprint.required_questions == []
    assert blueprint.brief.required_capabilities == ["예약 시간 선택"]
    assert blueprint.implementation_allowed is False
    assert blueprint.deployment_allowed is False
    assert blueprint.pattern_asset_digest.startswith("sha256:")


def test_incomplete_intent_stops_at_plain_language_questions():
    blueprint = build_blueprint(
        LaunchIntent(name="새 플랫폼", purpose="아이디어를 시험한다"),
        load_observations(EVIDENCE),
    )
    assert blueprint.next_step == "ASK_MINIMUM_QUESTIONS"
    assert blueprint.required_questions == ["audience", "core_action", "personal_data", "roles", "payment"]


def test_approval_gates_are_separate_and_ordered():
    stages = LaunchFlow().stages
    assert stages.index("SPEC_APPROVAL") < stages.index("SANDBOX_IMPLEMENTATION_APPROVAL")
    assert stages.index("SANDBOX_IMPLEMENTATION_APPROVAL") < stages.index("DEPLOYMENT_APPROVAL")


def test_asset_does_not_claim_unproven_fastest_and_has_usability_gate():
    asset = json.loads(
        (ROOT / "knowledge/platform-launch/arkaon-fast-launch-flow-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert asset["status"] == "INDEPENDENT_IMPLEMENTATION"
    assert "not proven fastest" in asset["claim_boundary"]
    assert asset["usability_benchmark"]["minimum_participants"] >= 5
    assert asset["usability_benchmark"]["promotion_gate"][
        "critical_misunderstanding_count_maximum"
    ] == 0
