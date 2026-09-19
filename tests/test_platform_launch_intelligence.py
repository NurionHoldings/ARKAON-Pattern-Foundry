import json
from pathlib import Path

import pytest

from apf.platform_launch_intelligence import (
    LaunchAnswer,
    LaunchFlow,
    LaunchIntelligenceError,
    LaunchIntent,
    OfficialFlowObservation,
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
