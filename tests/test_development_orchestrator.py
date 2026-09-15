from uuid import uuid4

import pytest

from apf.development_orchestrator import (
    DevelopmentOrchestrator,
    OrchestrationDenied,
    TaskKind,
    TaskResult,
    TaskStatus,
    Worker,
    build_delegation_plan,
    submit_plan,
    task_contract,
)


def contract(kind=TaskKind.RESEARCH, **changes):
    values = {
        "intent_fingerprint": "a" * 64,
        "objective": "find official precedents",
        "allowed_paths": ("docs/research/",),
        "expected_artifacts": ("evidence.json",),
    }
    values.update(changes)
    return task_contract(kind, **values)


def test_arkaon_can_claim_delegated_research_build_test_and_audit_work():
    orchestrator = DevelopmentOrchestrator()
    for kind in (TaskKind.RESEARCH, TaskKind.BUILD, TaskKind.TEST, TaskKind.AUDIT):
        submitted = orchestrator.submit(contract(kind))
        worker = Worker(f"arkaon-{kind.lower()}", frozenset({kind}))
        assert orchestrator.claim(worker).task_id == submitted.task_id


def test_intent_mutation_and_owned_asset_promotion_wait_for_human():
    orchestrator = DevelopmentOrchestrator()
    for kind in (TaskKind.MUTATE_INTENT, TaskKind.PROMOTE_OWNED_ASSET):
        submitted = orchestrator.submit(contract(kind))
        assert submitted.status == TaskStatus.BLOCKED_HUMAN_APPROVAL


def test_restricted_copy_and_authority_escalation_are_rejected():
    orchestrator = DevelopmentOrchestrator()
    with pytest.raises(OrchestrationDenied, match="PROHIBITED_OPERATION"):
        orchestrator.submit(
            contract(requested_operations=("COPY_RESTRICTED_SOURCE", "SELF_ESCALATE_AUTHORITY"))
        )


def test_dependency_blocks_work_until_predecessor_passes():
    orchestrator = DevelopmentOrchestrator()
    research = orchestrator.submit(contract())
    build = orchestrator.submit(contract(TaskKind.BUILD, dependencies=(research.task_id,)))
    builder = Worker("arkaon-builder", frozenset({TaskKind.BUILD}))
    assert orchestrator.claim(builder) is None
    scout = Worker("arkaon-scout", frozenset({TaskKind.RESEARCH}))
    claimed = orchestrator.claim(scout)
    orchestrator.complete(
        research.task_id,
        claimed.lease_token,
        TaskResult(("evidence.json",), ("provenance-check",), "PASS"),
    )
    assert orchestrator.claim(builder).task_id == build.task_id


def test_stale_worker_cannot_overwrite_task_result():
    orchestrator = DevelopmentOrchestrator()
    submitted = orchestrator.submit(contract())
    orchestrator.claim(Worker("scout", frozenset({TaskKind.RESEARCH})))
    with pytest.raises(OrchestrationDenied, match="STALE_LEASE"):
        orchestrator.complete(
            submitted.task_id,
            uuid4(),
            TaskResult(("evidence.json",), ("check",), "PASS"),
        )


def test_missing_artifact_or_check_fails_task():
    orchestrator = DevelopmentOrchestrator()
    submitted = orchestrator.submit(contract())
    claimed = orchestrator.claim(Worker("scout", frozenset({TaskKind.RESEARCH})))
    result = orchestrator.complete(
        submitted.task_id,
        claimed.lease_token,
        TaskResult((), (), "PASS"),
    )
    assert result.status == TaskStatus.FAILED


def test_goal_expands_into_complete_governed_delivery_chain():
    plan = build_delegation_plan(
        "implement reusable retry pattern",
        intent_fingerprint="a" * 64,
        allowed_paths=("src/", "tests/", "evidence/"),
    )
    assert tuple(task.kind for task in plan.tasks) == (
        TaskKind.RESEARCH,
        TaskKind.ANALYZE,
        TaskKind.ARCHITECT,
        TaskKind.BUILD,
        TaskKind.TEST,
        TaskKind.VERIFY,
        TaskKind.AUDIT,
        TaskKind.REGISTER_EVIDENCE,
        TaskKind.REPORT,
    )
    assert all(
        task.dependencies == (plan.tasks[index - 1].task_id,)
        for index, task in enumerate(plan.tasks[1:], start=1)
    )


def test_submitted_plan_releases_only_first_stage():
    orchestrator = DevelopmentOrchestrator()
    plan = build_delegation_plan(
        "deliver feature",
        intent_fingerprint="b" * 64,
        allowed_paths=("src/",),
    )
    submit_plan(orchestrator, plan)
    all_capabilities = Worker("arkaon", frozenset(TaskKind))
    claimed = orchestrator.claim(all_capabilities)
    assert claimed.kind == TaskKind.RESEARCH
    assert orchestrator.claim(all_capabilities) is None
