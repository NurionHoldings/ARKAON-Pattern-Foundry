from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import ConsoleSecurity
from apf.popular_format import Evidence, ProposalRequest


def test_owner_proposal_and_stale_decision(tmp_path):
    from apf.conversational_site_draft import ConversationalSiteDraftStore, SiteDraftRequest
    from apf.popular_format import ProposalStore

    tenant, owner, other = uuid4(), uuid4(), uuid4()
    sites = ConversationalSiteDraftStore(tmp_path)
    proposal_store = ProposalStore(tmp_path)
    app = create_app(
        console_security=ConsoleSecurity(environment="development", secret="unit-secret", allow_dev_sessions=True),
        conversational_site_draft_store=sites, format_proposal_store=proposal_store,
    )
    client = TestClient(app, base_url="https://testserver")
    def session(person, role="owner"):
        r = client.post("/console/dev/session", json={"tenant_id": str(tenant), "principal_id": str(person), "role": role})
        assert r.status_code == 200
        return r.json()["csrf_token"]
    csrf = session(owner)
    draft = sites.create(tenant_id=str(tenant), owner_principal_id=str(owner), request=SiteDraftRequest(name="Demo", request="A clear site for local customers"))
    identity = draft["intent_dna"]
    payload = ProposalRequest(
        artifact_type="site_draft", record_id=draft["draft_id"], asset_id=identity["asset_id"],
        source_revision_digest=draft["revisions"][-1]["revision_digest"],
        intent_digest=identity["intent_digest"], dna_digest=identity["dna_digest"],
        purpose="Explain service", audience="Local customers", brand_message="Meet our service",
        evidence=[Evidence(platform="youtube", url="https://www.youtube.com/watch?v=example",
                           observed_at=datetime.now(UTC), region="KR", category="services",
                           metric_scope="public view count", public_signal="manual observation only",
                           rights_status="reference_only", principle="clear opening message")],
    )
    response = client.post("/v1/console/format-proposals", json=payload.model_dump(mode="json"), headers={"X-CSRF-Token": csrf})
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert len(proposal["variants"]) == 3
    assert proposal["popularity"] == "POPULARITY_NOT_VERIFIED"
    session(other)
    assert client.get(f"/v1/console/format-proposals/{proposal['proposal_id']}").status_code == 404
    session(owner, "operator")
    assert client.get("/format-proposals").status_code == 403
    csrf = session(owner)
    decision = {"proposal_digest": proposal["proposal_digest"], "variant_id": "a", "decision": "APPROVE"}
    url = f"/v1/console/format-proposals/{proposal['proposal_id']}/decision"
    assert client.post(url, json=decision, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.post(url, json=decision, headers={"X-CSRF-Token": csrf}).status_code == 409


def test_reference_url_rejects_foreign_host():
    with pytest.raises(ValueError):
        Evidence(platform="youtube", url="https://youtube.com.evil.example/watch", observed_at=datetime.now(UTC),
                 region="KR", category="services", metric_scope="public views", public_signal="manual count",
                 rights_status="reference_only", principle="brief opening line")
