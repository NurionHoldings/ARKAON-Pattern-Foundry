import pytest
from pydantic import ValidationError

from apf.call_template import CallTemplateRequest, build_call_template


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
