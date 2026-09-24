from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import ConsoleSecurity
from apf.conversational_site_draft import ConversationalSiteDraftStore
from apf.design_reference_urls import DesignReferenceStore
from apf.public_page_observer import ObservationError, PublicPageObserver, extract_observation
from apf.reference_material_consent import REQUIRED_ACKNOWLEDGEMENTS, ReferenceConsentStore
from apf.repository import MemoryRepository


class FakeObserver(PublicPageObserver):
    def __init__(self):
        self.visits = []

    def _get(self, url, *, limit, media_type):
        self.visits.append(url)
        if media_type == "text/html":
            return (b'<html><head><link rel="stylesheet" href="/style.css">'
                    b'<link rel="stylesheet" href="https://other.example.com/x.css">'
                    b'</head></html>')
        return b":root {--primary:#145a7a}body{background:#f3f0e8;color:#172536;gap:32px}"


def test_observer_uses_same_origin_css_and_returns_only_derived_values():
    observer = FakeObserver()
    result = observer.observe("https://example.com/", uuid4())
    assert result["source_kind"] == "STATIC_HTML_AND_SAME_ORIGIN_CSS"
    assert result["background"] == "#f3f0e8"
    assert result["text"] == "#172536"
    assert result["accent"] == "#145a7a"
    assert result["density"] == "airy"
    assert observer.visits == ["https://example.com/", "https://example.com/style.css"]
    assert "source_digest" in result and "css" not in result


def test_dns_rejects_mixed_public_and_private_answers(monkeypatch):
    def answers(*args, **kwargs):
        return [(2, 1, 6, "", ("8.8.8.8", 443)),
                (2, 1, 6, "", ("127.0.0.1", 443))]
    monkeypatch.setattr("apf.public_page_observer.socket.getaddrinfo", answers)
    with pytest.raises(ObservationError, match="NON_PUBLIC_ADDRESS"):
        PublicPageObserver()._resolve("example.com")


def test_extractor_requires_actual_style_signals():
    with pytest.raises(ObservationError, match="NO_STYLE_SIGNALS"):
        extract_observation("<html>hello</html>", "", uuid4())


def test_capture_requires_scope_bound_receipt_and_owner(tmp_path):
    fake = FakeObserver()
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(environment="test", secret="s" * 32,
                                         allow_dev_sessions=True),
        conversational_site_draft_store=ConversationalSiteDraftStore(tmp_path),
        design_reference_store=DesignReferenceStore(tmp_path),
        reference_consent_store=ReferenceConsentStore(tmp_path),
        public_page_observer=fake,
    )
    client = TestClient(app, base_url="https://testserver")
    owner, tenant = uuid4(), uuid4()
    csrf = client.post("/console/dev/session", json={
        "tenant_id": str(tenant), "principal_id": str(owner), "role": "owner",
    }).json()["csrf_token"]
    draft = client.post("/v1/console/site-drafts", headers={"X-CSRF-Token": csrf},
                        json={"name": "디자인", "request": "화면 디자인 생성"}).json()
    base = f'/v1/console/design-references/site_draft/{draft["draft_id"]}'
    refs = client.post(base, headers={"X-CSRF-Token": csrf}, json={
        "urls": [{"url": "https://example.com/"}],
    }).json()
    ref = refs["references"][0]["reference_id"]
    payload = {"based_on_set_digest": refs["set_digest"],
               "reference_id": ref, "consent_request_id": str(uuid4())}
    assert client.post(base + "/capture", headers={"X-CSRF-Token": csrf},
                       json=payload).status_code == 403
    assert fake.visits == []
    request = {
        "request_id": payload["consent_request_id"], "source_id": ref,
        "source_locator": "https://example.com/", "mode": "PRINCIPLE_REFERENCE",
        "rights_basis": "UNKNOWN", "requested_paths": ["design-observation"],
        "intended_use": "공개 색상 구성의 원리만 관찰하고 자체 디자인을 생성합니다.",
        "scope_digest": refs["set_digest"],
    }
    receipt = client.post("/v1/console/reference-material-consents",
                          headers={"X-CSRF-Token": csrf}, json={
                              "request": request,
                              "acknowledged_items": sorted(REQUIRED_ACKNOWLEDGEMENTS),
                              "nonce": str(uuid4()),
                          })
    assert receipt.status_code == 201
    assert client.post(base + "/capture", json=payload).status_code == 403
    capture = client.post(base + "/capture", headers={"X-CSRF-Token": csrf},
                          json=payload)
    assert capture.status_code == 200, capture.text
    assert capture.json()["background"] == "#f3f0e8"
    assert fake.visits
    client.post("/console/dev/session", json={
        "tenant_id": str(tenant), "principal_id": str(uuid4()), "role": "owner",
    })
    assert client.post(base + "/capture", headers={"X-CSRF-Token": csrf},
                       json=payload).status_code != 200
