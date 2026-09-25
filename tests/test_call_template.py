from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apf.api import create_app
from apf.call_template import CallTemplateRequest, build_call_template
from apf.console import ConsoleSecurity
from apf.repository import MemoryRepository


def request(**changes):
    values = {
        "tenant_id": "tenant-a", "owner_id": "owner-a", "slug": "my-voice",
        "display_name": "홍길동", "introduction": "안녕하세요. 소개 페이지입니다.",
        "purpose_prompts": ["상담", "자료 요청"], "material_titles": ["소개서"],
    }
    return CallTemplateRequest(**(values | changes))


def test_draft_is_reproducible_and_not_a_live_call():
    first = build_call_template(request())
    assert first == build_call_template(request())
    assert first.content_digest.startswith("sha256:")
    assert first.publication_state == "DRAFT"
    assert first.telephony_state == "NOT_CONNECTED"
    assert not first.implementation_allowed and not first.deployment_allowed
    assert [menu.menu_id for menu in first.menus] == [
        "introduction", "purpose", "materials", "next_step"
    ]
    assert first.session_contract["menu_navigation"] == "server_authorized_broadcast_to_both"


def test_content_and_owner_change_produce_distinct_assets():
    base = build_call_template(request())
    assert build_call_template(request(owner_id="owner-b")).content_digest != base.content_digest
    assert build_call_template(request(introduction="새 소개")).content_digest != base.content_digest


@pytest.mark.parametrize("change", [
    {"slug": "../../other"},
    {"display_name": "<script>bad</script>"},
    {"purpose_prompts": ["상담", "상담"]},
    {"material_titles": [" "]},
])
def test_rejects_unsafe_or_ambiguous_template(change):
    with pytest.raises(ValidationError):
        request(**change)


def test_disabling_calls_keeps_message_route():
    result = build_call_template(request(allow_call_request=False))
    assert result.menus[-1].actions == ["leave_message", "owner_decide"]


def test_console_generates_owner_bound_preview_with_csrf():
    app = create_app(repository=MemoryRepository(), console_security=ConsoleSecurity(
        environment="test", secret="s" * 32, allow_dev_sessions=True,
    ))
    client = TestClient(app, base_url="https://testserver")
    tenant_id, owner_id = str(uuid4()), str(uuid4())
    session = client.post("/console/dev/session", json={
        "tenant_id": tenant_id, "principal_id": owner_id, "role": "owner",
    })
    assert client.get("/call-template").status_code == 200
    payload = request().model_dump(exclude={"tenant_id", "owner_id"})
    assert client.post("/v1/console/call-templates/preview", json=payload).status_code == 403
    result = client.post("/v1/console/call-templates/preview", json=payload, headers={
        "X-CSRF-Token": session.json()["csrf_token"],
    })
    assert result.status_code == 200
    assert result.json()["tenant_id"] == tenant_id
    assert result.json()["owner_id"] == owner_id
    assert result.json()["publication_state"] == "DRAFT"
    client.post("/console/dev/session", json={
        "tenant_id": tenant_id, "principal_id": str(uuid4()), "role": "operator",
    })
    assert client.get("/call-template").status_code == 403
