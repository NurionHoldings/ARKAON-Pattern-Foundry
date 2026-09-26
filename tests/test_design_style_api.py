from uuid import uuid4

from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import ConsoleSecurity
from apf.conversational_site_draft import ConversationalSiteDraftStore
from apf.design_reference_urls import DesignReferenceStore
from apf.design_style_proposal import StyleProposalStore
from apf.repository import MemoryRepository


def test_owner_can_preview_and_apply_style_without_publishing(tmp_path):
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(environment="test", secret="s" * 32,
                                         allow_dev_sessions=True),
        conversational_site_draft_store=ConversationalSiteDraftStore(tmp_path),
        design_reference_store=DesignReferenceStore(tmp_path),
        style_proposal_store=StyleProposalStore(tmp_path),
    )
    client = TestClient(app, base_url="https://testserver")
    tenant, owner = uuid4(), uuid4()
    csrf = client.post("/console/dev/session", json={
        "tenant_id": str(tenant), "principal_id": str(owner), "role": "owner",
    }).json()["csrf_token"]
    created = client.post("/v1/console/site-drafts", headers={"X-CSRF-Token": csrf},
                          json={"name": "부업장터", "request": "새로운 참여 경험을 소개하는 화면"}).json()
    subject = created["draft_id"]
    base = f"/v1/console/design-references/site_draft/{subject}"
    original = client.get(f"/v1/console/site-drafts/{subject}/revisions/1/preview.html").text
    assert "--apf-gap" not in original
    references = client.post(base, headers={"X-CSRF-Token": csrf}, json={
        "urls": [{"url": "https://example.com/", "focus": "배경"}],
        "based_on_digest": None,
    }).json()
    ref = references["references"][0]["reference_id"]
    payload = {"based_on_set_digest": references["set_digest"], "observations": [{
        "reference_id": ref, "background": "#faf8f1",
        "text": "#192b3d", "accent": "#217963",
        "layout": "split", "density": "airy",
    }]}
    assert client.post(base + "/style", json=payload).status_code == 403
    proposed = client.post(base + "/style", headers={"X-CSRF-Token": csrf},
                           json=payload)
    assert proposed.status_code == 200
    proposal = proposed.json()
    assert proposal["status"] == "PREVIEW_REQUIRED"
    responsive = client.get(base + "/style/preview/home")
    assert responsive.status_code == 200
    assert "--apf-gap:32px" in responsive.text
    assert "--apf-gap" not in client.get(
        f"/v1/console/site-drafts/{subject}/revisions/1/preview.html"
    ).text
    assert client.post(base + "/style/decision", headers={"X-CSRF-Token": csrf},
                       json={"proposal_digest": proposal["proposal_digest"],
                             "decision": "APPLY"}).json()["status"] == "APPLIED"
    applied = client.get(f"/v1/console/site-drafts/{subject}/revisions/1/preview.html")
    assert "--apf-gap:32px" in applied.text
    assert client.get(f"/v1/console/site-drafts/{subject}").json()[
        "automatic_deployment"
    ] is False
    client.post("/console/dev/session", json={
        "tenant_id": str(tenant), "principal_id": str(uuid4()), "role": "owner",
    })
    assert client.get(base + "/style").status_code != 200
