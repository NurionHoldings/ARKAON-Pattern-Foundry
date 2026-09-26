import httpx
import pytest

from apf.railway_actions import execute, preview
from apf.railway_provider import RailwayClient, RailwayProviderError

PROJECT = "fc475a70-51d8-41e4-9820-05c3d1677674"
ENVIRONMENT = "38194820-d44e-4498-a61e-1f9555bb7eee"


def provider(*, bad_scope=False, fail_create=False):
    services = [{"id": "existing", "name": "Postgres"}]
    calls = []

    def handler(request):
        assert request.url == "https://backboard.railway.com/graphql/v2"
        assert request.headers["Project-Access-Token"] == "test-secret"
        body = __import__("json").loads(request.content)
        calls.append(body["query"])
        if "projectToken" in body["query"]:
            return httpx.Response(200, json={"data": {"projectToken": {
                "projectId": "wrong" if bad_scope else PROJECT,
                "environmentId": ENVIRONMENT,
            }}})
        if "serviceCreate" in body["query"]:
            if fail_create:
                return httpx.Response(200, json={"errors": [{"message": "denied"}]})
            service = {"id": "created", "name": body["variables"]["input"]["name"]}
            services.append(service)
            return httpx.Response(200, json={"data": {"serviceCreate": service}})
        return httpx.Response(200, json={"data": {"project": {
            "id": PROJECT, "name": "sandbox", "services": {
                "edges": [{"node": service} for service in services],
            }, "environments": {"edges": [{"node": {
                "id": ENVIRONMENT, "name": "staging",
            }}]},
        }}})

    client = RailwayClient("test-secret", PROJECT, ENVIRONMENT,
                           transport=httpx.MockTransport(handler))
    return client, calls


def test_live_read_verifies_project_token_scope_and_never_leaks_token():
    client, calls = provider()
    snapshot = client.snapshot()
    assert snapshot["source"] == "RAILWAY_API_LIVE"
    assert snapshot["services"] == [{"id": "existing", "name": "Postgres"}]
    assert len(calls) == 2
    wrong, calls = provider(bad_scope=True)
    with pytest.raises(RailwayProviderError, match="scope"):
        wrong.snapshot()
    assert len(calls) == 1


def test_create_requires_single_use_preview_and_readback(tmp_path, monkeypatch):
    monkeypatch.setenv("APF_RAILWAY_ACTION_SECRET", "s" * 32)
    monkeypatch.setenv("APF_RUNTIME_ROOT", str(tmp_path))
    client, calls = provider()
    action = preview(client, "my-empty-service", "owner")
    assert action["action"] == "CREATE_EMPTY_SERVICE"
    assert not any("serviceCreate" in query for query in calls)
    result = execute(client, action["approval_token"], "owner")
    assert result["status"] == "VERIFIED_EMPTY_SERVICE"
    with pytest.raises(RailwayProviderError, match="already used"):
        execute(client, action["approval_token"], "owner")
    with pytest.raises(RailwayProviderError, match="invalid"):
        execute(client, action["approval_token"], "other-owner")


def test_graphql_error_consumes_approval_and_requires_recheck(tmp_path, monkeypatch):
    monkeypatch.setenv("APF_RAILWAY_ACTION_SECRET", "s" * 32)
    monkeypatch.setenv("APF_RUNTIME_ROOT", str(tmp_path))
    client, _ = provider(fail_create=True)
    token = preview(client, "my-empty-service", "owner")["approval_token"]
    with pytest.raises(RailwayProviderError, match="returned an error"):
        execute(client, token, "owner")
    with pytest.raises(RailwayProviderError, match="already used"):
        execute(client, token, "owner")
