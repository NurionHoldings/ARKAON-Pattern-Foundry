from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from apf.admin_change_control import (
    AdminChangeController,
    ChangeControlRejected,
    ChangeProposalStatus,
    ChangeScope,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def scopes() -> tuple[ChangeScope, ...]:
    return (
        ChangeScope("recommendation", "진행 안내 개선", ("preview: 단계 표시",)),
        ChangeScope("synthetic-tests", "합성시험", ("합성 사용성 시험",)),
    )


@pytest.fixture
def foundry(tmp_path: Path) -> Path:
    root = tmp_path / "foundry"
    (root / "config").mkdir(parents=True)
    (root / "state" / "change-control").mkdir(parents=True)
    (root / "config" / "arkaon-admin-change-control.json").write_text(
        (Path(__file__).resolve().parents[1] / "config" / "arkaon-admin-change-control.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return root


def controller(foundry: Path) -> AdminChangeController:
    return AdminChangeController(foundry_root=foundry)


def test_apply_without_approval_is_forbidden(foundry: Path) -> None:
    value = controller(foundry)
    with pytest.raises(ChangeControlRejected, match="without operator approval"):
        value.apply_without_approval()


def test_auto_merge_or_deploy_is_forbidden(foundry: Path) -> None:
    value = controller(foundry)
    with pytest.raises(ChangeControlRejected, match="merge or deploy"):
        value.auto_merge_or_deploy()


def test_preview_required_before_eternian_review(foundry: Path) -> None:
    value = controller(foundry)
    value.create_proposal(
        proposal_id="change-1",
        platform_id="DEMO",
        source_digest=digest("source"),
        summary="진행 안내 개선 제안",
        scopes=scopes(),
        now=NOW,
    )
    with pytest.raises(ChangeControlRejected, match="preview required"):
        value.record_eternian_review("change-1", review_digest=digest("review"))


def test_closed_loop_preview_eternian_operator_partial_apply_and_rollback(foundry: Path) -> None:
    value = controller(foundry)
    value.create_proposal(
        proposal_id="change-1",
        platform_id="DEMO",
        source_digest=digest("source"),
        summary="진행 안내 개선 제안",
        scopes=scopes(),
        now=NOW,
        case_id="refl-DEMO-f1",
    )
    preview = value.preview("change-1")
    assert preview.preview_only is True
    value.record_eternian_review("change-1", review_digest=digest("review"))
    value.operator_approve(
        "change-1",
        scope_ids=("recommendation",),
        decision_digest=digest("operator"),
    )
    record = value.apply_partial("change-1", now=NOW)
    assert record.intent_only is True
    assert record.applied_scope_ids == ("recommendation",)
    rolled = value.rollback(record.rollback_token)
    assert rolled.status is ChangeProposalStatus.ROLLED_BACK


def test_partial_apply_requires_operator_approval(foundry: Path) -> None:
    value = controller(foundry)
    value.create_proposal(
        proposal_id="change-1",
        platform_id="DEMO",
        source_digest=digest("source"),
        summary="진행 안내 개선 제안",
        scopes=scopes(),
        now=NOW,
    )
    value.preview("change-1")
    value.record_eternian_review("change-1", review_digest=digest("review"))
    with pytest.raises(ChangeControlRejected, match="operator approval"):
        value.apply_partial("change-1", now=NOW)


def test_operational_data_is_blocked(foundry: Path) -> None:
    value = controller(foundry)
    with pytest.raises(ChangeControlRejected, match="operational or identity"):
        value.create_proposal(
            proposal_id="change-1",
            platform_id="DEMO",
            source_digest=digest("source"),
            summary="member order handling",
            scopes=scopes(),
            now=NOW,
        )
