from uuid import uuid4
from xml.etree import ElementTree

import pytest

from apf.business_card import (
    BusinessCardError,
    BusinessCardRequest,
    BusinessCardRevisionRequest,
    BusinessCardStore,
)
from apf.logo_draft import LogoDraftRequest, LogoDraftStore, LogoRevisionRequest


def logo(store, tenant, owner):
    return store.create(
        tenant_id=tenant,
        owner_principal_id=owner,
        request=LogoDraftRequest(
            name="안전<svg onload=1>", tagline="문구", color="#2563eb", shape="orbit"
        ),
    )


def request(logo_id, **changes):
    value = {
        "logo_draft_id": logo_id,
        "name": "김<인석>",
        "title": "대표",
        "phone": "010-0000-0000",
        "email": "hello@example.com",
        "brand_text": "ARKAON",
    }
    return BusinessCardRequest(**(value | changes))


def test_business_card_snapshots_owner_logo_escapes_svg_and_rolls_back(tmp_path):
    tenant, owner = str(uuid4()), str(uuid4())
    logos = LogoDraftStore(tmp_path)
    source = logo(logos, tenant, owner)
    store = BusinessCardStore(tmp_path, logos)
    created = store.create(
        tenant_id=tenant, owner_principal_id=owner, request=request(source["draft_id"])
    )
    first = created["revisions"][0]
    assert (
        created["generation"] == "DETERMINISTIC_VECTOR_ONLY"
        and created["credit_meter"] == "UNAVAILABLE"
    )
    assert "&lt;인석&gt;" in first["front_svg"]
    ElementTree.fromstring(first["front_svg"])
    ElementTree.fromstring(first["back_svg"])
    revised = store.revise(
        created["card_id"],
        tenant_id=tenant,
        owner_principal_id=owner,
        request=BusinessCardRevisionRequest(
            **request(source["draft_id"], title="디렉터").model_dump(),
            based_on_revision_digest=first["revision_digest"],
            change_note="직함 수정",
        ),
    )
    restored = store.rollback(
        created["card_id"],
        1,
        tenant_id=tenant,
        owner_principal_id=owner,
        based_on_revision_digest=revised["revision_digest"],
    )
    assert restored["revision_number"] == 3 and restored["title"] == "대표"
    svg, filename = store.download(
        created["card_id"], "back", tenant_id=tenant, owner_principal_id=owner
    )
    assert filename.endswith("-back.svg") and "ARKAON" in svg


def test_business_card_requires_owned_logo_and_latest_digest(tmp_path):
    tenant, owner = str(uuid4()), str(uuid4())
    logos = LogoDraftStore(tmp_path)
    source = logo(logos, tenant, owner)
    store = BusinessCardStore(tmp_path, logos)
    with pytest.raises(BusinessCardError, match="LOGO_NOT_FOUND"):
        store.create(
            tenant_id=tenant, owner_principal_id=str(uuid4()), request=request(source["draft_id"])
        )
    card = store.create(
        tenant_id=tenant, owner_principal_id=owner, request=request(source["draft_id"])
    )
    with pytest.raises(BusinessCardError, match="NOT_FOUND"):
        store.get(card["card_id"], tenant_id=tenant, owner_principal_id=str(uuid4()))
    with pytest.raises(BusinessCardError, match="STALE_REVISION"):
        store.rollback(
            card["card_id"],
            1,
            tenant_id=tenant,
            owner_principal_id=owner,
            based_on_revision_digest="sha256:" + "0" * 64,
        )


def test_nested_logo_variants_render_and_rollback_uses_historical_svg_snapshot(tmp_path):
    tenant, owner = str(uuid4()), str(uuid4())
    logos = LogoDraftStore(tmp_path)
    source = logo(logos, tenant, owner)
    first_logo = source["revisions"][0]
    second_logo = logos.revise(
        source["draft_id"],
        tenant_id=tenant,
        owner_principal_id=owner,
        request=LogoRevisionRequest(
            based_on_revision_digest=first_logo["revision_digest"],
            name="안전",
            tagline="문구",
            color="#2563eb",
            shape="orbit",
            selected_variant=2,
            change_note="시안 2 선택",
        ),
    )
    store = BusinessCardStore(tmp_path, logos)
    card = store.create(
        tenant_id=tenant, owner_principal_id=owner, request=request(source["draft_id"])
    )
    original = card["revisions"][0]
    for side in ("front_svg", "back_svg"):
        ElementTree.fromstring(original[side])
    third_logo = logos.revise(
        source["draft_id"],
        tenant_id=tenant,
        owner_principal_id=owner,
        request=LogoRevisionRequest(
            based_on_revision_digest=second_logo["revision_digest"],
            name="안전",
            tagline="문구",
            color="#e11d48",
            shape="spark",
            selected_variant=3,
            change_note="시안 3 선택",
        ),
    )
    changed = store.revise(
        card["card_id"],
        tenant_id=tenant,
        owner_principal_id=owner,
        request=BusinessCardRevisionRequest(
            **request(source["draft_id"], title="새 직함").model_dump(),
            based_on_revision_digest=original["revision_digest"],
            change_note="로고 최신본 반영",
        ),
    )
    for side in ("front_svg", "back_svg"):
        ElementTree.fromstring(changed[side])
    restored = store.rollback(
        card["card_id"],
        1,
        tenant_id=tenant,
        owner_principal_id=owner,
        based_on_revision_digest=changed["revision_digest"],
    )
    assert restored["front_svg"] == original["front_svg"]
    assert restored["back_svg"] == original["back_svg"]
    assert third_logo["selected_variant"] == 3


def test_business_card_malformed_document_fails_closed(tmp_path):
    tenant, owner = str(uuid4()), str(uuid4())
    logos = LogoDraftStore(tmp_path)
    source = logo(logos, tenant, owner)
    store = BusinessCardStore(tmp_path, logos)
    card = store.create(
        tenant_id=tenant, owner_principal_id=owner, request=request(source["draft_id"])
    )
    store._path(card["card_id"]).write_text("[]", encoding="utf-8")
    with pytest.raises(BusinessCardError, match="TAMPERED"):
        store.get(card["card_id"], tenant_id=tenant, owner_principal_id=owner)


def test_unsaved_card_preview_uses_owned_logo_without_writing_contact_state(tmp_path):
    tenant, owner = str(uuid4()), str(uuid4())
    logos = LogoDraftStore(tmp_path)
    source = logo(logos, tenant, owner)
    store = BusinessCardStore(tmp_path, logos)
    draft = store.preview(
        tenant_id=tenant, owner_principal_id=owner, request=request(source["draft_id"])
    )
    assert "&lt;인석&gt;" in draft["front_svg"]
    ElementTree.fromstring(draft["back_svg"])
    assert not (tmp_path / "state" / "business-cards").exists()
    with pytest.raises(BusinessCardError, match="LOGO_NOT_FOUND"):
        store.preview(
            tenant_id=tenant,
            owner_principal_id=str(uuid4()),
            request=request(source["draft_id"]),
        )
