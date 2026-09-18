from datetime import UTC, datetime, timedelta

import pytest

from apf.evidence_capability import CollectedEvidence, EvidenceKind
from apf.self_improvement import (
    ImprovementActor,
    ImprovementState,
    ImprovementWorkflowError,
    detect_self_improvement,
    post_self_improvement,
    transition_improvement,
)

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def evidence(**changes) -> CollectedEvidence:
    values = {
        "kind": EvidenceKind.PUBLIC_SNS,
        "provenance_complete": True,
        "authorization_valid": True,
        "license_compatible": True,
        "consent_valid": True,
        "independently_verified": True,
        "fresh": True,
        "contains_sensitive_data": False,
        "confidence_percent": 85,
        "independent_source_count": 2,
    }
    values.update(changes)
    return CollectedEvidence(**values)


def request():
    return detect_self_improvement(
        request_id="improvement-001",
        now=NOW,
        intent_dna="Improve ARKAON without bypassing owner authority.",
        capability_gap="Repeated inbox packets lack feedback control.",
        evidence_refs=("sha256:" + "a" * 64, "sha256:" + "b" * 64),
        proposed_change="Add semantic deduplication and queue backpressure.",
        expected_benefit="Reduce duplicate review effort.",
        risks=("A real change could be suppressed by an incorrect fingerprint.",),
        validation_plan=("Run duplicate and changed-evidence test vectors.",),
        evidence=evidence(),
    )


def move(item, desired, actor, seconds, approval=None):
    return transition_improvement(
        item,
        desired=desired,
        actor=actor,
        expected_revision=item.revision,
        now=NOW + timedelta(seconds=seconds),
        owner_approval_digest=approval,
    )


def test_full_owner_governed_improvement_flow(tmp_path) -> None:
    item, path = post_self_improvement(request(), inbox_root=tmp_path, now=NOW)
    assert path.is_file()
    assert item.state is ImprovementState.INBOX_POSTED

    item = move(item, ImprovementState.ETERNIAN_REVIEWING, ImprovementActor.ETERNIAN, 1)
    item = move(item, ImprovementState.OWNER_APPROVAL_PENDING, ImprovementActor.ETERNIAN, 2)
    item = move(
        item,
        ImprovementState.OWNER_APPROVED,
        ImprovementActor.OWNER,
        3,
        approval=item.scope_digest(),
    )
    item = move(item, ImprovementState.SANDBOX_IMPLEMENTING, ImprovementActor.ARKAON, 4)
    item = move(item, ImprovementState.VERIFIED, ImprovementActor.VERIFIER, 5)
    item = move(item, ImprovementState.CHANGE_REPORTED, ImprovementActor.ARKAON, 6)
    item = move(
        item,
        ImprovementState.DEPLOYMENT_APPROVAL_PENDING,
        ImprovementActor.OWNER,
        7,
    )

    assert item.state is ImprovementState.DEPLOYMENT_APPROVAL_PENDING
    assert item.production_change_allowed is False
    assert item.deployment_allowed is False


def test_arkaon_cannot_implement_before_owner_approval(tmp_path) -> None:
    item, _ = post_self_improvement(request(), inbox_root=tmp_path, now=NOW)
    with pytest.raises(ImprovementWorkflowError, match="IMPROVEMENT_TRANSITION_FORBIDDEN"):
        move(item, ImprovementState.SANDBOX_IMPLEMENTING, ImprovementActor.ARKAON, 1)


def test_wrong_actor_cannot_approve_owner_change(tmp_path) -> None:
    item, _ = post_self_improvement(request(), inbox_root=tmp_path, now=NOW)
    item = move(item, ImprovementState.ETERNIAN_REVIEWING, ImprovementActor.ETERNIAN, 1)
    item = move(item, ImprovementState.OWNER_APPROVAL_PENDING, ImprovementActor.ETERNIAN, 2)
    with pytest.raises(ImprovementWorkflowError, match="IMPROVEMENT_ACTOR_FORBIDDEN"):
        move(
            item,
            ImprovementState.OWNER_APPROVED,
            ImprovementActor.ETERNIAN,
            3,
            approval=item.scope_digest(),
        )


def test_owner_approval_is_bound_to_exact_scope(tmp_path) -> None:
    item, _ = post_self_improvement(request(), inbox_root=tmp_path, now=NOW)
    item = move(item, ImprovementState.ETERNIAN_REVIEWING, ImprovementActor.ETERNIAN, 1)
    item = move(item, ImprovementState.OWNER_APPROVAL_PENDING, ImprovementActor.ETERNIAN, 2)
    with pytest.raises(
        ImprovementWorkflowError,
        match="OWNER_APPROVAL_SCOPE_DIGEST_REQUIRED",
    ):
        move(
            item,
            ImprovementState.OWNER_APPROVED,
            ImprovementActor.OWNER,
            3,
            approval="0" * 64,
        )


def test_low_evidence_cannot_create_improvement_request() -> None:
    with pytest.raises(
        ImprovementWorkflowError,
        match="EVIDENCE_NOT_READY_FOR_IMPROVEMENT_REQUEST",
    ):
        detect_self_improvement(
            request_id="blocked",
            now=NOW,
            intent_dna="intent",
            capability_gap="gap",
            evidence_refs=("sha256:" + "a" * 64,),
            proposed_change="change",
            expected_benefit="benefit",
            risks=(),
            validation_plan=("test",),
            evidence=evidence(independently_verified=False, independent_source_count=1),
        )


def test_duplicate_request_id_cannot_change_scope(tmp_path) -> None:
    item, _ = post_self_improvement(request(), inbox_root=tmp_path, now=NOW)
    changed = item.__class__(
        **{
            **item.__dict__,
            "state": ImprovementState.DETECTED,
            "revision": 0,
            "proposed_change": "Different unauthorized scope.",
        }
    )
    with pytest.raises(ImprovementWorkflowError, match="REQUEST_ID_SCOPE_CONFLICT"):
        post_self_improvement(changed, inbox_root=tmp_path, now=NOW)
