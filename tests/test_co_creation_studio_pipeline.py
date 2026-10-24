import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from apf.co_creation_codegen import CoCreationCodegenEngine
from apf.co_creation_product_improvement import CoCreationProductImprovementEngine
from apf.co_creation_reference_gate import (
    ReferenceGateRejected,
    assert_reference_consent_or_raise,
    reference_scope_digest,
    verify_receipt_integrity,
)
from apf.co_creation_studio import (
    CoCreationStudioRejected,
    StudioBrief,
    assert_valid_session_id,
    brief_has_empty_sections,
    build_studio_brief_from_conversation,
    load_studio_draft,
    render_filled_section_html,
    save_studio_draft,
)
from apf.conversational_co_creation import (
    CoCreationProposal,
    CoCreationScope,
    ConversationalCoCreationEngine,
    EvidenceRef,
    TemplateSectionBlueprint,
)
from apf.reference_material_consent import NOTICE_TEXT, NOTICE_VERSION
from apf.reference_material_consent import digest as reference_digest

NOW = datetime(2031, 9, 1, tzinfo=UTC)


def _receipt_document(
    *,
    request_id: str,
    scope_digest: str,
    principal_id: str,
    decision_code: str = "REFERENCE_ANALYSIS_ALLOWED",
) -> dict[str, object]:
    request_digest = "sha256:" + "a" * 64
    consent_digest = "sha256:" + "b" * 64
    decision: dict[str, object] = {
        "decision": decision_code,
        "reason": "USER_REQUEST_AND_NOTICE_CONFIRMED",
        "allowed_mode": "PRINCIPLE_REFERENCE",
        "request_digest": request_digest,
        "consent_digest": consent_digest,
        "direct_expression_reuse_allowed": False,
        "implementation_allowed": decision_code == "SANDBOX_IMPLEMENTATION_ALLOWED",
        "merge_allowed": False,
        "deployment_allowed": False,
        "modification_proposals": [],
    }
    receipt: dict[str, object] = {
        "schema_version": "apf.reference-material-consent-receipt/1.0",
        "request_id": request_id,
        "scope_digest": scope_digest,
        "request_digest": request_digest,
        "consent_digest": consent_digest,
        "principal_id": principal_id,
        "notice_version": NOTICE_VERSION,
        "notice_digest": reference_digest(NOTICE_TEXT),
        "decision": decision,
    }
    receipt["receipt_digest"] = reference_digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    return receipt


def _write_policy(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "arkaon-conversational-co-creation.json").write_text(
        json.dumps({"schema_version": "apf.conversational-co-creation/v1"}),
        encoding="utf-8",
    )
    (config / "arkaon-proposal-quality.json").write_text(
        json.dumps({"schema_version": "apf.proposal-quality/v1", "minimum_proposal_quality_score": 0.2}),
        encoding="utf-8",
    )
    (config / "arkaon-co-creation-codegen.json").write_text(
        json.dumps({"schema_version": "apf.co-creation-codegen/v1", "require_scaffold_manifest": False}),
        encoding="utf-8",
    )


def _seed_patterns(tmp_path: Path) -> None:
    patterns = tmp_path / "knowledge" / "landing-structure-patterns" / "proposed"
    patterns.mkdir(parents=True)
    (patterns / "hero.json").write_text(
        json.dumps(
            {
                "schema_version": "apf.landing-structure-pattern-proposal/v1",
                "pattern_id": "hero",
                "pattern_token": "landing-pattern:hero-single-cta",
                "summary": "hero",
                "evidence_digests": ["a" * 64],
            }
        ),
        encoding="utf-8",
    )


def test_brief_from_conversation_has_no_empty_sections():
    message = (
        "이름: 온유 스튜디오\n"
        "고객: 브랜드를 처음 시작하는 작은 가게\n"
        "목적: 가게 이야기를 전달하는 홈페이지\n"
        "차별점: 작은 화면에서도 읽기 쉬운 구성\n"
        "연락: studio@example.com"
    )
    proposal = CoCreationProposal(
        proposal_id="p" * 24,
        session_id=str(uuid4()),
        tenant_id=str(uuid4()),
        principal_id=str(uuid4()),
        platform_id="DEMO",
        scope=CoCreationScope.TEMPLATE,
        domain_brief="brief",
        recommended_structure=("hero",),
        copy_angle_options=("a",),
        evidence_table=(EvidenceRef("K", "r", "d" * 64, "s"),),
        template_blueprint=(
            TemplateSectionBlueprint("hero", "value", "landing-pattern:hero-single-cta", True),
        ),
        platform_blueprint=(),
        synthesis_test_plan=("t",),
        assistant_reply="ok",
        proposal_digest="x" * 64,
    )
    brief = build_studio_brief_from_conversation(message=message, scope="TEMPLATE", proposal=proposal)
    ok, gaps = brief_has_empty_sections(brief)
    assert ok, gaps
    assert brief.title == "온유 스튜디오"
    assert "studio@example.com" in brief.contact


def test_sync_and_codegen_use_filled_sections_not_comment_stubs(tmp_path):
    _write_policy(tmp_path)
    _seed_patterns(tmp_path)
    tenant, principal = str(uuid4()), str(uuid4())
    digest = sha256(f"{tenant}|{principal}|DEMO|paid".encode()).hexdigest()
    engine = ConversationalCoCreationEngine(foundry_root=tmp_path)
    proposal = engine.chat(
        tenant_id=tenant,
        principal_id=principal,
        platform_id="DEMO",
        message="이름: 데모 가게\n고객: 동네 주민\n목적: 메뉴 소개\n차별점: 신선한 재료\n연락: demo@example.com",
        scope=CoCreationScope.TEMPLATE,
        payment_entitlement_digest=digest,
        now=NOW,
    )
    draft = load_studio_draft(tmp_path, proposal.session_id)
    assert draft is not None
    codegen = CoCreationCodegenEngine(foundry_root=tmp_path)
    manifest = codegen.run_codegen(
        proposal_id=proposal.proposal_id,
        operator_approval_digest="b" * 64,
        now=NOW,
    )
    hero_path = tmp_path / "state" / "co-creation" / "codegen" / proposal.proposal_id / "sections" / "hero.html"
    content = hero_path.read_text(encoding="utf-8")
    assert "data-filled=\"true\"" in content
    assert "copy-angle slot" not in content
    assert manifest.codegen_status == "GENERATED"


def test_product_improvement_rejects_trace_without_deliverable_gain(tmp_path):
    brief = StudioBrief(
        industry="service",
        title="테스트",
        audience="고객",
        story="서비스 소개",
        offerings="상담 | 범위를 정리합니다.\n디자인 | 초안을 만듭니다.\n점검 | 수정합니다.",
        difference="차별점",
        process="상담\n초안\n수정",
        contact="test@example.com",
    )
    engine = CoCreationProductImprovementEngine(foundry_root=tmp_path)
    weak_candidate = "<html><body><h1>테스트</h1><p>짧은 소개</p></body></html>"
    evaluation = engine.evaluate(
        session_id="s" * 24,
        proposal_id="p" * 24,
        brief=brief,
        candidate_html=weak_candidate,
        now=NOW,
    )
    assert evaluation.improvement_accepted is False
    assert evaluation.automated_check_passed is False
    assert evaluation.status_display == "자동 검사 미통과"
    assert evaluation.derived_learning_task_id
    assert evaluation.scoring_artifact_ref


def test_product_improvement_automated_pass_does_not_accept_improvement(tmp_path):
    brief = StudioBrief(
        industry="service",
        title="테스트",
        audience="고객",
        story="서비스 소개",
        offerings="상담 | 범위를 정리합니다.\n디자인 | 초안을 만듭니다.\n점검 | 수정합니다.",
        difference="차별점",
        process="상담\n초안\n수정",
        contact="test@example.com",
    )
    engine = CoCreationProductImprovementEngine(foundry_root=tmp_path)
    strong_candidate = (
        "<html><head><style>@media(max-width:650px){body{padding:0}}</style></head>"
        "<body><section class=\"section\"><h1>테스트</h1></section>"
        "<section><ol><li>1</li><li>2</li><li>3</li></ol></section>"
        "<section><p>긴 설명</p></section></body></html>"
    )
    evaluation = engine.evaluate(
        session_id="s" * 24,
        proposal_id="p" * 24,
        brief=brief,
        candidate_html=strong_candidate,
        now=NOW,
    )
    assert evaluation.automated_check_passed is True
    assert evaluation.improvement_accepted is False
    assert evaluation.status_display == "자동 검사 통과·독립 검토 대기"
    assert evaluation.independent_review_status == "PENDING"


def test_save_studio_draft_rejects_incomplete_brief(tmp_path):
    brief = StudioBrief(
        industry="service",
        title="",
        audience="고객",
        story="story",
        offerings="항목 | 설명",
        difference="diff",
        process="step",
        contact="c",
    )
    from apf.co_creation_studio import CoCreationStudioRejected

    with pytest.raises(CoCreationStudioRejected):
        save_studio_draft(
            foundry_root=tmp_path,
            session_id=str(uuid4()),
            proposal_id="p" * 24,
            tenant_id=str(uuid4()),
            principal_id=str(uuid4()),
            brief=brief,
            now=NOW,
        )


def test_studio_draft_isolated_by_session(tmp_path):
    brief = StudioBrief(
        industry="service",
        title="A",
        audience="B",
        story="C",
        offerings="X | Y",
        difference="D",
        process="1\n2",
        contact="e@example.com",
    )
    session_a, session_b = str(uuid4()), str(uuid4())
    save_studio_draft(
        foundry_root=tmp_path,
        session_id=session_a,
        proposal_id="p" * 24,
        tenant_id=str(uuid4()),
        principal_id=str(uuid4()),
        brief=brief,
        now=NOW,
    )
    assert load_studio_draft(tmp_path, session_a) is not None
    assert load_studio_draft(tmp_path, session_b) is None


def test_reference_consent_blocks_missing_receipt(tmp_path):
    with pytest.raises(ReferenceGateRejected) as error:
        assert_reference_consent_or_raise(
            foundry_root=tmp_path,
            principal_id=str(uuid4()),
            message="참고 https://example.com/design",
            reference_site_url=None,
            feature_reference_urls=None,
            reference_consent_request_id=None,
            intended_use="landing draft",
        )
    assert error.value.code == "REFERENCE_CONSENT_REQUIRED"


def test_reference_consent_rejects_scope_mismatch(tmp_path):
    request_id = "req-scope-test"
    wrong_scope = reference_scope_digest(urls=("https://example.com/b",), intended_use="use-b")
    receipt_dir = tmp_path / "state" / "reference-material-consents"
    receipt_dir.mkdir(parents=True)
    principal = str(uuid4())
    (receipt_dir / f"{request_id}.json").write_text(
        json.dumps(_receipt_document(request_id=request_id, scope_digest=wrong_scope, principal_id=principal)),
        encoding="utf-8",
    )
    with pytest.raises(ReferenceGateRejected) as error:
        assert_reference_consent_or_raise(
            foundry_root=tmp_path,
            principal_id=principal,
            message="https://example.com/a",
            reference_site_url="https://example.com/a",
            feature_reference_urls=None,
            reference_consent_request_id=request_id,
            intended_use="use-a",
        )
    assert error.value.code == "REFERENCE_CONSENT_SCOPE_MISMATCH"


def test_session_id_invalid_rejected_not_sanitized(tmp_path):
    with pytest.raises(CoCreationStudioRejected) as error:
        assert_valid_session_id("aa/bb")
    assert error.value.code == "SESSION_ID_INVALID"
    session_a = str(uuid4())
    session_b = str(uuid4())
    brief = StudioBrief(
        industry="service",
        title="A",
        audience="B",
        story="C",
        offerings="X | Y",
        difference="D",
        process="1",
        contact="e@example.com",
    )
    save_studio_draft(
        foundry_root=tmp_path,
        session_id=session_a,
        proposal_id="p" * 24,
        tenant_id=str(uuid4()),
        principal_id=str(uuid4()),
        brief=brief,
        now=NOW,
    )
    assert load_studio_draft(tmp_path, session_b) is None


def test_receipt_integrity_rejects_tampered_digest():
    receipt = _receipt_document(request_id="r1", scope_digest="sha256:" + "c" * 64, principal_id=str(uuid4()))
    receipt["receipt_digest"] = "sha256:" + "d" * 64
    ok, reason = verify_receipt_integrity(receipt)
    assert not ok
    assert reason == "RECEIPT_DIGEST_MISMATCH"


def test_render_filled_section_includes_title_and_body():
    brief = StudioBrief(
        industry="service",
        title="온유",
        audience="작은 가게",
        story="이야기",
        offerings="상담 | 메시지 정리",
        difference="차별",
        process="1단계\n2단계",
        contact="mail@example.com",
    )
    html = render_filled_section_html(section_id="hero", purpose="value", brief=brief)
    assert "<h1>" in html
    assert "온유" in html
    assert "작은 가게" in html
