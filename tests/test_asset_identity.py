from uuid import uuid4

from apf.asset_identity import make_asset_identity
from apf.business_card import BusinessCardRequest, BusinessCardStore
from apf.conversational_site_draft import ConversationalSiteDraftStore, SiteDraftRequest
from apf.logo_draft import LogoDraftRequest, LogoDraftStore, LogoRevisionRequest
from apf.visual_platform_dialogue import PlatformBrief, VisualPlatformDialogueStore


def test_identity_is_owner_bound_stable_and_private():
    tenant, owner, item = str(uuid4()), str(uuid4()), str(uuid4())
    values = {
        "tenant_id": tenant, "owner_principal_id": owner,
        "artifact_type": "logo_svg", "artifact_id": item,
        "original_intent": {"purpose": "brand_logo"},
        "dna": {"shape": "orbit"},
    }
    first = make_asset_identity(**values)
    assert first == make_asset_identity(**values)
    assert first["source_record_id"] == item
    assert first["deployment_state"] == "NOT_CONNECTED"
    assert first["asset_id"] != make_asset_identity(
        **(values | {"owner_principal_id": str(uuid4())})
    )["asset_id"]


def test_created_artifacts_expose_resume_identity_without_contacts(tmp_path):
    tenant, owner = str(uuid4()), str(uuid4())
    logos = LogoDraftStore(tmp_path)
    logo = logos.create(
        tenant_id=tenant, owner_principal_id=owner,
        request=LogoDraftRequest(
            name="상표명", tagline="비공개 문구", color="#2563eb", shape="orbit",
        ),
    )
    logo_identity = logo["intent_dna"]
    assert logo_identity["source_record_id"] == logo["draft_id"]
    revised = logos.revise(
        logo["draft_id"], tenant_id=tenant, owner_principal_id=owner,
        request=LogoRevisionRequest(
            name="수정명", tagline="다른 문구", color="#e11d48", shape="spark",
            based_on_revision_digest=logo["revisions"][0]["revision_digest"],
            selected_variant=2, change_note="수정 확인",
        ),
    )
    assert revised["revision_number"] == 2
    assert logos.get(
        logo["draft_id"], tenant_id=tenant, owner_principal_id=owner,
    )["intent_dna"] == logo_identity

    cards = BusinessCardStore(tmp_path, logos)
    card = cards.create(
        tenant_id=tenant, owner_principal_id=owner,
        request=BusinessCardRequest(
            logo_draft_id=logo["draft_id"], name="개인 이름", title="대표",
            phone="010-1234-5678", email="private@example.com", brand_text="상표명",
        ),
    )
    identity_text = str(card["intent_dna"])
    assert card["intent_dna"]["dna"]["logo_draft_id"] == logo["draft_id"]
    assert "010-1234-5678" not in identity_text
    assert "private@example.com" not in identity_text

    sites = ConversationalSiteDraftStore(tmp_path)
    site = sites.create(
        tenant_id=tenant, owner_principal_id=owner,
        request=SiteDraftRequest(name="브랜드", request="비공개 기획 요청"),
    )
    assert site["intent_dna"]["source_record_id"] == site["draft_id"]
    assert "비공개 기획 요청" not in str(site["intent_dna"])

    dialogues = VisualPlatformDialogueStore(tmp_path)
    platform = dialogues.create(
        tenant_id=tenant, owner_principal_id=owner,
        brief=PlatformBrief(
            name="플랫폼", purpose="비공개 사업 목적", audience=["참여자"],
            required_capabilities=["검색"], constraints=[],
        ),
    )
    assert platform["intent_dna"]["source_record_id"] == platform["dialogue_id"]
    assert "비공개 사업 목적" not in str(platform["intent_dna"])
