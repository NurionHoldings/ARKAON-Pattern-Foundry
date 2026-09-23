from uuid import uuid4

import pytest

from apf.conversational_site_draft import (
    ConversationalSiteDraftStore,
    SiteDraftError,
    SiteDraftRequest,
    SiteDraftRevisionRequest,
)


def setup(tmp_path):
    store = ConversationalSiteDraftStore(tmp_path)
    tenant, owner = str(uuid4()), str(uuid4())
    value = store.create(
        tenant_id=tenant,
        owner_principal_id=owner,
        request=SiteDraftRequest(
            name="부업장터",
            request="참여자가 벌거리를 찾는 따뜻한 소개 홈페이지를 만들어줘. <script>alert(1)</script>",
        ),
    )
    return store, tenant, owner, value["draft_id"]


def test_korean_request_is_escaped_and_never_deployable(tmp_path):
    store, tenant, owner, draft_id = setup(tmp_path)
    page = store.preview(draft_id, 1, tenant_id=tenant, owner_principal_id=owner)
    assert "&lt;script&gt;" in page and "<script>alert" not in page
    detail = store.get(draft_id, tenant_id=tenant, owner_principal_id=owner)
    assert detail["automatic_implementation"] is False and detail["automatic_deployment"] is False
    approval = store.request_approval(draft_id, tenant_id=tenant, owner_principal_id=owner)
    assert approval["implementation_allowed"] is False and approval["deployment_allowed"] is False
    assert (
        store.get(draft_id, tenant_id=tenant, owner_principal_id=owner)["state"]
        == "OWNER_APPROVAL_PENDING"
    )


def test_revision_and_rollback_are_versioned_and_tenant_bound(tmp_path):
    store, tenant, owner, draft_id = setup(tmp_path)
    first = store.get(draft_id, tenant_id=tenant, owner_principal_id=owner)["revisions"][0]
    second = store.revise(
        draft_id,
        tenant_id=tenant,
        owner_principal_id=owner,
        request=SiteDraftRevisionRequest(
            based_on_revision_digest=first["revision_digest"],
            change_note="제목과 소개 문구를 바꾼 이유",
            title="지금 시작하는 부업장터",
            description="내게 맞는 벌거리를 한눈에 찾아보세요.",
        ),
    )
    rolled = store.rollback(draft_id, tenant_id=tenant, owner_principal_id=owner, revision_number=1)
    assert second["revision_number"] == 2 and rolled["revision_number"] == 3
    assert "지금 시작하는 부업장터" in second["html"]
    assert "내게 맞는 벌거리" in second["html"]
    assert rolled["based_on_revision_digest"] == second["revision_digest"]
    assert "웹사이트 초안 · v3" in rolled["html"]
    with pytest.raises(SiteDraftError, match="NOT_FOUND"):
        store.preview(draft_id, 1, tenant_id=str(uuid4()), owner_principal_id=owner)


def test_tampered_ledger_is_rejected(tmp_path):
    store, tenant, owner, draft_id = setup(tmp_path)
    path = tmp_path / "state" / "conversational-site-drafts" / f"{draft_id}.json"
    path.write_text(
        path.read_text().replace('"automatic_deployment": false', '"automatic_deployment": true'),
        encoding="utf-8",
    )
    with pytest.raises(SiteDraftError, match="TAMPERED"):
        store.get(draft_id, tenant_id=tenant, owner_principal_id=owner)


def test_same_tenant_other_owner_cannot_read_detail_or_preview(tmp_path):
    store, tenant, _owner, draft_id = setup(tmp_path)
    intruder = str(uuid4())
    with pytest.raises(SiteDraftError, match="NOT_FOUND"):
        store.get(draft_id, tenant_id=tenant, owner_principal_id=intruder)
    with pytest.raises(SiteDraftError, match="NOT_FOUND"):
        store.preview(draft_id, 1, tenant_id=tenant, owner_principal_id=intruder)


def test_external_connection_readiness_is_guidance_only(tmp_path):
    store, tenant, owner, draft_id = setup(tmp_path)
    readiness = store.get(draft_id, tenant_id=tenant, owner_principal_id=owner)[
        "external_connection_readiness"
    ]
    assert readiness["mode"] == "GUIDANCE_ONLY"
    assert readiness["github"]["account"] == "SIGN_UP_REQUIRED"
    assert readiness["github"]["connection_feature"] == "NOT_AVAILABLE"
    assert readiness["meshy"]["api_access"] == "NOT_CONFIGURED"
    assert readiness["netlify"]["github_app"] == "NOT_CONNECTED"
    assert all(value is False for value in readiness["controls"].values())
    assert "api_key" not in readiness and "password" not in readiness
    path = tmp_path / "state" / "conversational-site-drafts" / f"{draft_id}.json"
    assert "external_connection_readiness" not in path.read_text(encoding="utf-8")


def test_legacy_draft_without_readiness_keeps_its_valid_digest_and_gets_guidance(tmp_path):
    store, tenant, owner, draft_id = setup(tmp_path)
    path = tmp_path / "state" / "conversational-site-drafts" / f"{draft_id}.json"
    document = __import__("json").loads(path.read_text(encoding="utf-8"))
    # Model a schema 1.0 document created before readiness existed.
    document.pop("external_connection_readiness", None)
    document.pop("draft_digest")
    from apf.conversational_site_draft import _digest

    document["draft_digest"] = _digest(document)
    path.write_text(__import__("json").dumps(document), encoding="utf-8")
    detail = store.get(draft_id, tenant_id=tenant, owner_principal_id=owner)
    assert detail["external_connection_readiness"]["mode"] == "GUIDANCE_ONLY"


def test_previous_persisted_readiness_variant_is_compatible_but_not_trusted(tmp_path):
    from apf.conversational_site_draft import _LEGACY_EXTERNAL_CONNECTION_READINESS, _digest

    store, tenant, owner, draft_id = setup(tmp_path)
    path = tmp_path / "state" / "conversational-site-drafts" / f"{draft_id}.json"
    document = __import__("json").loads(path.read_text(encoding="utf-8"))
    document["external_connection_readiness"] = _LEGACY_EXTERNAL_CONNECTION_READINESS
    document.pop("draft_digest")
    document["draft_digest"] = _digest(document)
    path.write_text(__import__("json").dumps(document), encoding="utf-8")
    readiness = store.get(draft_id, tenant_id=tenant, owner_principal_id=owner)[
        "external_connection_readiness"
    ]
    assert readiness["github"]["connection_feature"] == "NOT_AVAILABLE"
    assert "app_installation" not in readiness["github"]
