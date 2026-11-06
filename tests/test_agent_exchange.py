import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from apf.agent_exchange import accept_result, authorize_one, digest, poll, prepare, submit


def request():
    fields = {"request_id": "test-agent-request", "intent_dna": "自家 개선 테스트",
              "capability_gap": "TEST_DOUBLE: gallery improvement", "evidence_refs": ["fixture"],
              "proposed_change": "sandbox only", "expected_benefit": "verify before adoption",
              "risks": ["regression"], "validation_plan": ["tests"], "source_tier": "PROPOSE_ONLY"}
    return {**fields, "schema_version": "apf.self-improvement-request/1.0", "state": "INBOX_POSTED",
            "scope_digest": digest(fields), "production_change_allowed": False,
            "automatic_merge_allowed": False, "deployment_allowed": False}


def build():
    return prepare(request(), actor="ARKAON", branch="sandbox/test", expected_sha="a" * 40)


def authorization(task):
    return {"decision": "AUTHORIZE_ONE_BILLABLE_TASK", "task_digest": task["task_digest"],
            "command_digest": task["command_digest"], "approver": "TEST_OPERATOR",
            "approved_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}


def result(task, **override):
    return {"task_digest": task["task_digest"], "actor": task["actor"],
            "request_id": task["request_id"], "scope_digest": task["scope_digest"],
            "tested_head": "b" * 40, "worker_id": "build-worker", "evidence_digest": "c" * 64,
            "merge_allowed": False, "deployment_allowed": False, **override}


def signed(data, key):
    return {"result": data, "signature": hmac.new(key, digest(data).encode(), "sha256").hexdigest()}


def test_prepared_command_uses_project_and_new_branch_provider_flow():
    task = build()
    assert task["command"][1] == "agents:create"
    assert task["command"][-3:] == ["--project", "arkaonfoundry", "--json"]
    assert task["merge_allowed"] is False


def test_missing_or_changed_billing_authorization_blocks():
    task = build()
    with pytest.raises(ValueError):
        authorize_one(task, {}, now=datetime.now(UTC))
    auth = authorization(task)
    task["command"][7] = "other-branch"
    with pytest.raises(ValueError):
        authorize_one(task, auth, now=datetime.now(UTC))


def test_expired_cost_permission_blocks():
    task = build()
    auth = authorization(task)
    auth["expires_at"] = "2020-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        authorize_one(task, auth, now=datetime.now(UTC))


def test_submit_claim_prevents_a_second_billable_call(tmp_path, monkeypatch):
    monkeypatch.setattr("apf.agent_exchange.shutil.which", lambda _: "/usr/bin/netlify")
    monkeypatch.setattr("apf.agent_exchange.verify_remote_head", lambda task: None)
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"id":"provider-123"}', stderr="")
    task = build()
    assert submit(task, authorization(task), tmp_path, runner=runner)["status"] == "SUBMITTED"
    with pytest.raises(FileExistsError):
        submit(task, authorization(task), tmp_path, runner=runner)
    assert len(calls) == 1


def test_ambiguous_provider_response_is_not_silently_retried(tmp_path, monkeypatch):
    monkeypatch.setattr("apf.agent_exchange.shutil.which", lambda _: "/usr/bin/netlify")
    monkeypatch.setattr("apf.agent_exchange.verify_remote_head", lambda task: None)
    task = build()
    runner = lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{"unknown":true}', stderr="")
    assert submit(task, authorization(task), tmp_path, runner=runner)["status"].endswith("RECONCILIATION")
    with pytest.raises(FileExistsError):
        submit(task, authorization(task), tmp_path, runner=runner)


def test_poll_done_never_means_independent_audit_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("apf.agent_exchange.shutil.which", lambda _: "/usr/bin/netlify")
    monkeypatch.setattr("apf.agent_exchange.verify_remote_head", lambda task: None)
    runner = lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{"id":"test-task","status":"done"}')
    event = poll(build(), "test-task", tmp_path, runner=runner)
    assert event["status"] == "RESULT_REVIEW_PENDING"
    assert event["audit_accepted"] is False
    assert len(list((tmp_path / "inbox/agent-exchange").glob("*.json"))) == 1


def test_cross_role_key_and_scope_substitution_rejected(tmp_path):
    task = build()
    data = result(task)
    with pytest.raises(ValueError):
        accept_result(task, signed(data, b"a" * 32), tmp_path, role_key=b"b" * 32)
    data["scope_digest"] = "d" * 64
    with pytest.raises(ValueError):
        accept_result(task, signed(data, b"a" * 32), tmp_path, role_key=b"a" * 32)


def test_audit_requires_implementation_and_different_worker_and_evidence(tmp_path):
    with pytest.raises(ValueError):
        prepare(request(), actor="ETERNIAN_AUDIT_WORKER", branch="sandbox/result", expected_sha="b" * 40)
    implementation = result(build())
    task = prepare(request(), actor="ETERNIAN_AUDIT_WORKER", branch="sandbox/result", expected_sha="b" * 40,
                   implementation_ref=implementation)
    same = result(task)
    with pytest.raises(ValueError):
        accept_result(task, signed(same, b"z" * 32), tmp_path, role_key=b"z" * 32)
    good = result(task, worker_id="audit-worker", evidence_digest="e" * 64)
    accepted = accept_result(task, signed(good, b"z" * 32), tmp_path, role_key=b"z" * 32)
    assert accepted["status"] == "AUTHENTICATED_RESULT_RECEIVED"
    assert accepted["audit_accepted"] is False


def test_invalid_branch_cannot_inject_cli_options():
    with pytest.raises(ValueError):
        prepare(request(), actor="ARKAON", branch="--token=x", expected_sha="a" * 40)


def test_no_secret_values_in_preflight(monkeypatch):
    from apf.agent_exchange import preflight
    monkeypatch.setenv("APF_ARKAON_RESULT_KEY", "s" * 64)
    report = preflight()
    assert report["arkaon_result_key_configured"] is True
    assert "s" * 64 not in json.dumps(report)
    assert report["chatgpt_auto_wakeup"] is False


def test_provider_never_inherits_role_or_database_secrets(monkeypatch):
    from apf.agent_exchange import provider_environment
    monkeypatch.setenv("APF_ETERNIAN_RESULT_KEY", "secret")
    monkeypatch.setenv("DATABASE_URL", "private")
    environment = provider_environment()
    assert "APF_ETERNIAN_RESULT_KEY" not in environment
    assert "DATABASE_URL" not in environment


def test_courier_skips_finished_history_and_reaches_new_task(tmp_path, monkeypatch):
    from apf.agent_exchange import courier_cycle
    state = tmp_path / "state/agent-exchange"
    for index in range(31):
        directory = state / f"{index:03}"
        directory.mkdir(parents=True)
        (directory / "submission-result.json").write_text('{}')
        (directory / "provider-terminal.json").write_text('{}')
    task = build()
    directory = state / "z-new"
    directory.mkdir()
    (directory / "submission-result.json").write_text(json.dumps({"status": "SUBMITTED",
        "task_digest": task["task_digest"], "provider_task_id": "remote-task"}))
    (directory / "task.json").write_text(json.dumps(task))
    monkeypatch.setattr("apf.agent_exchange.poll", lambda *args: {"provider_status": "done", "audit_accepted": False})
    assert courier_cycle(tmp_path)["polled"] == 1
    assert (directory / "provider-terminal.json").exists()
    assert courier_cycle(tmp_path)["polled"] == 0


def test_remote_head_change_blocks_before_any_paid_call(tmp_path, monkeypatch):
    monkeypatch.setattr("apf.agent_exchange.shutil.which", lambda _: "/usr/bin/netlify")
    def changed(task):
        raise ValueError("REMOTE_HEAD_CHANGED")
    monkeypatch.setattr("apf.agent_exchange.verify_remote_head", changed)
    task = build()
    with pytest.raises(ValueError, match="REMOTE_HEAD_CHANGED"):
        submit(task, authorization(task), tmp_path, runner=lambda *a, **kw: pytest.fail("billable call"))
    assert not list(tmp_path.rglob("submission-claim.json"))


def test_provider_keeps_required_node_proxy_setting(monkeypatch):
    from apf.agent_exchange import provider_environment
    monkeypatch.setenv("NODE_USE_ENV_PROXY", "1")
    assert provider_environment()["NODE_USE_ENV_PROXY"] == "1"


def test_actual_cli_state_field_is_supported(tmp_path, monkeypatch):
    monkeypatch.setattr("apf.agent_exchange.shutil.which", lambda _: "/usr/bin/netlify")
    runner = lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{"id":"test-task","state":"running"}')
    assert poll(build(), "test-task", tmp_path, runner=runner)["provider_status"] == "running"


def test_provider_manages_branches_and_requires_workspace_evidence():
    task = build()
    assert task["workspace_strategy"] == "NETLIFY_MANAGED"
    assert task["agent_git_writes_allowed"] is False
    prompt = task["command"][3]
    assert "Netlify manages result branches and commits" in prompt
    assert "Do not run git switch" in prompt
    assert "hash tested files and logs" in prompt
    assert "Do not invent a final" in prompt


def test_legacy_task_can_be_polled_but_cannot_be_billed(tmp_path, monkeypatch):
    from apf.agent_exchange import validate_task
    task = build()
    task["schema_version"] = "apf.agent-exchange-task/v1"
    task.pop("workspace_strategy")
    task.pop("agent_git_writes_allowed")
    task["task_digest"] = digest({k: v for k, v in task.items() if k != "task_digest"})
    validate_task(task)
    with pytest.raises(ValueError, match="legacy task"):
        authorize_one(task, authorization(task), now=datetime.now(UTC))
    monkeypatch.setattr("apf.agent_exchange.shutil.which", lambda _: "/usr/bin/netlify")
    runner = lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{"id":"historic","state":"done"}')
    assert poll(task, "historic", tmp_path, runner=runner)["audit_accepted"] is False


def test_workspace_strategy_cannot_be_changed_even_with_recomputed_digest():
    from apf.agent_exchange import validate_task
    task = build()
    task["agent_git_writes_allowed"] = True
    task["task_digest"] = digest({k: v for k, v in task.items() if k != "task_digest"})
    with pytest.raises(ValueError, match="provider-managed"):
        validate_task(task)
