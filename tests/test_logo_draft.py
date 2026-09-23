from uuid import uuid4
from xml.etree import ElementTree

import pytest

from apf.logo_draft import (
    LogoDraftError,
    LogoDraftRequest,
    LogoDraftStore,
    LogoRevisionRequest,
)


def make(store, tenant, owner, name="마루<svg onload=alert(1)>"):
    return store.create(
        tenant_id=tenant,
        owner_principal_id=owner,
        request=LogoDraftRequest(
            name=name, tagline="일상을 가볍게", color="#2563eb", shape="orbit"
        ),
    )


def test_logo_is_deterministic_escaped_and_round_trips(tmp_path):
    store, tenant, owner = LogoDraftStore(tmp_path), str(uuid4()), str(uuid4())
    created = make(store, tenant, owner)
    assert created["artifact_type"] == "logo_svg" and created["credit_cap"] == 500
    assert created["credit_meter"] == "UNAVAILABLE"
    svg = created["revisions"][0]["variants"][0]["svg"]
    assert "&lt;svg" in svg and "onload=alert" in svg
    first = created["revisions"][0]
    second = store.revise(
        created["draft_id"],
        tenant_id=tenant,
        owner_principal_id=owner,
        request=LogoRevisionRequest(
            based_on_revision_digest=first["revision_digest"],
            name="마루",
            tagline="새 문구",
            color="#e11d48",
            shape="spark",
            selected_variant=3,
            change_note="색상과 문구 수정",
        ),
    )
    assert second["selected_variant"] == 3 and len(second["variants"]) == 3
    restored = store.rollback(
        created["draft_id"],
        1,
        tenant_id=tenant,
        owner_principal_id=owner,
        based_on_revision_digest=second["revision_digest"],
    )
    assert restored["revision_number"] == 3 and restored["selected_variant"] == 1
    downloaded, filename = store.download(
        created["draft_id"], tenant_id=tenant, owner_principal_id=owner
    )
    assert filename.endswith(".svg") and "마루" in downloaded


def test_other_owner_cannot_read_or_download_logo(tmp_path):
    store, tenant, owner = LogoDraftStore(tmp_path), str(uuid4()), str(uuid4())
    draft = make(store, tenant, owner)
    for operation in (
        lambda: store.get(draft["draft_id"], tenant_id=tenant, owner_principal_id=str(uuid4())),
        lambda: store.download(
            draft["draft_id"], tenant_id=tenant, owner_principal_id=str(uuid4())
        ),
    ):
        with pytest.raises(LogoDraftError, match="NOT_FOUND"):
            operation()


def test_rollback_requires_latest_digest_and_xml_only_characters(tmp_path):
    store, tenant, owner = LogoDraftStore(tmp_path), str(uuid4()), str(uuid4())
    created = make(store, tenant, owner, name="마루\ufffe\x01")
    first = created["revisions"][0]
    svg = first["variants"][0]["svg"]
    assert "\ufffe" not in svg and "\x01" not in svg
    ElementTree.fromstring(svg)
    store.revise(
        created["draft_id"],
        tenant_id=tenant,
        owner_principal_id=owner,
        request=LogoRevisionRequest(
            based_on_revision_digest=first["revision_digest"],
            name="마루",
            tagline="새 문구",
            color="#2563eb",
            shape="arch",
            selected_variant=2,
            change_note="새 버전",
        ),
    )
    with pytest.raises(LogoDraftError, match="STALE_REVISION"):
        store.rollback(
            created["draft_id"],
            1,
            tenant_id=tenant,
            owner_principal_id=owner,
            based_on_revision_digest=first["revision_digest"],
        )
