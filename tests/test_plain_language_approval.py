import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apf.plain_language_approval import (
    ApprovalDecision,
    PlainApprovalError,
    PlainLanguageApprovalStore,
    canonical_scope,
    digest,
    validate_report,
)


def report():
    value = {
        "schema_version": "apf.self-improvement-request/1.0",
        "request_id": "plain-approval-001",
        "state": "APPROVAL_PENDING",
        "intent_dna": "Keep owner control.",
        "capability_gap": "A damaged packet can stop later work.",
        "evidence_refs": ["sha256:" + "a" * 64],
        "proposed_change": "Isolate the damaged packet and continue.",
        "expected_benefit": "Healthy requests continue.",
        "risks": ["A valid packet could be held by mistake."],
        "validation_plan": ["Prove later packets continue."],
        "source_tier": "VERIFIED",
        "production_change_allowed": False,
        "automatic_merge_allowed": False,
        "deployment_allowed": False,
        "approval_scope": {
            "allowed_paths": ["src/apf/relay.py", "tests/test_relay.py"],
            "allowed_operations": ["READ_WORKTREE", "WRITE_WORKTREE", "RUN_TESTS"],
        },
    }
    value["scope_digest"] = digest(canonical_scope(value))
    plain = {
        "scope_digest": value["scope_digest"],
        "title": "손상 요청을 따로 보관합니다",
        "problem": "잘못된 요청 하나가 뒤의 정상 요청도 멈춥니다.",
        "change": "잘못된 요청만 격리합니다.",
        "benefit": "정상 요청은 계속 처리됩니다.",
        "impact": "개인정보·금전·운영 배포 영향이 없습니다.",
        "rollback": "변경 커밋을 되돌립니다.",
        "risks": ["정상 요청을 잘못 격리할 수 있습니다."],
        "risk_level": "낮음",
        "visual": {
            "before": ["손상 요청 도착", "전체 처리 중단"],
            "after": ["손상 요청 격리", "정상 요청 계속 처리"],
        },
    }
    value["plain_language"] = plain
    review = {
        "state": "ETERNIAN_VERIFIED",
        "reviewer": "에테르니언",
        "reviewer_role": "ETERNIAN",
        "reviewed_at": "2026-09-19T12:00:00+09:00",
        "scope_digest": value["scope_digest"],
        "plain_digest": digest(plain),
    }
    review["review_digest"] = digest(review)
    value["semantic_review"] = review
    return value


def store_with_report(tmp_path):
    path = tmp_path / "state/plain-language-approval-reports/plain-approval-001.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(report(), ensure_ascii=False), encoding="utf-8")
    return PlainLanguageApprovalStore(tmp_path)


def decision(**changes):
    values = {
        "decision": "APPROVE",
        "scope_digest": report()["scope_digest"],
        "nonce": uuid4(),
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }
    values.update(changes)
    return ApprovalDecision(**values)


def test_valid_report_exposes_plain_content_and_visual_steps(tmp_path):
    store = store_with_report(tmp_path)
    listed = store.list_reports()
    assert listed[0]["title"] == "손상 요청을 따로 보관합니다"
    detail = store.get_report("plain-approval-001")
    assert detail["plain_language"]["visual"]["after"][-1] == "정상 요청 계속 처리"
    assert detail["deployment_allowed"] is False


@pytest.mark.parametrize("tamper", ["scope", "plain", "review"])
def test_tampered_scope_explanation_or_semantic_review_is_blocked(tamper):
    value = report()
    if tamper == "scope":
        value["proposed_change"] = "expanded change"
    elif tamper == "plain":
        value["plain_language"]["impact"] = "위험 없음"
    else:
        value["semantic_review"]["reviewer"] = "self"
    with pytest.raises(PlainApprovalError):
        validate_report(value)


def test_click_decision_is_durable_idempotent_and_scope_bound(tmp_path):
    store = store_with_report(tmp_path)
    item = decision()
    first = store.decide(
        request_id="plain-approval-001", decision=item, principal_id="owner-1"
    )
    second = store.decide(
        request_id="plain-approval-001", decision=item, principal_id="owner-1"
    )
    assert first == second
    assert first["receipt_digest"] == digest(
        {key: value for key, value in first.items() if key != "receipt_digest"}
    )
    assert first["automatic_merge_allowed"] is False
    with pytest.raises(PlainApprovalError, match="ALREADY_DECIDED"):
        store.decide(
            request_id="plain-approval-001", decision=decision(), principal_id="owner-1"
        )


def test_expired_or_wrong_scope_decision_is_denied(tmp_path):
    store = store_with_report(tmp_path)
    with pytest.raises(PlainApprovalError, match="EXPIRED"):
        store.decide(
            request_id="plain-approval-001",
            decision=decision(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
            principal_id="owner-1",
        )
    with pytest.raises(PlainApprovalError, match="SCOPE_MISMATCH"):
        store.decide(
            request_id="plain-approval-001",
            decision=decision(scope_digest="b" * 64),
            principal_id="owner-1",
        )
