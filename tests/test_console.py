import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import apf.console as console_module
from apf.api import create_app
from apf.console import SESSION_COOKIE, ConsoleSecurity
from apf.domain import AnalysisTargetCreate
from apf.plain_language_approval import PlainLanguageApprovalStore
from apf.reference_material_consent import (
    REQUIRED_ACKNOWLEDGEMENTS,
    ReferenceConsentStore,
)
from apf.repository import MemoryRepository
from apf.visual_platform_dialogue import VisualPlatformDialogueStore


def make_client(*, role: str = "operator", approval_store=None):
    repository = MemoryRepository()
    app = create_app(
        repository=repository,
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
        plain_approval_store=approval_store,
    )
    client = TestClient(app, base_url="https://testserver")
    tenant_id, principal_id = uuid4(), uuid4()
    response = client.post(
        "/console/dev/session",
        json={"tenant_id": str(tenant_id), "principal_id": str(principal_id), "role": role},
    )
    assert response.status_code == 200
    return client, repository, tenant_id, response.json()["csrf_token"]


def target_payload(tenant_id, name="MJN"):
    return AnalysisTargetCreate.model_validate(
        {
            "tenant_id": str(tenant_id),
            "name": name,
            "target_type": "OWNED_SYSTEM",
            "classification": "INTERNAL",
            "permissions": {"read": True, "parse": True, "derive": True},
            "source_evidence_ids": [str(uuid4())],
        }
    )


def test_reference_material_notice_checkboxes_and_receipt_are_owner_bound(tmp_path):
    tenant_id, owner_id = uuid4(), uuid4()
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
        reference_consent_store=ReferenceConsentStore(tmp_path),
    )
    client = TestClient(app, base_url="https://testserver")
    session = client.post(
        "/console/dev/session",
        json={"tenant_id": str(tenant_id), "principal_id": str(owner_id), "role": "owner"},
    )
    csrf = session.json()["csrf_token"]
    page = client.get("/reference-material-consent")
    assert page.status_code == 200
    assert "참고자료 사용 확인" in page.text
    notice = client.get("/v1/console/reference-material-notice")
    assert notice.status_code == 200
    assert set(notice.json()["required_acknowledgements"]) == REQUIRED_ACKNOWLEDGEMENTS
    payload = {
        "request": {
            "request_id": "reference-ui-001",
            "source_id": "official-page",
            "source_locator": "https://example.org/product",
            "intended_use": "기능 원리만 참고하여 독립적인 이용 흐름을 구현한다.",
            "mode": "CLEAN_ROOM_IMPLEMENTATION",
            "rights_basis": "UNKNOWN",
            "rights_evidence_digest": None,
            "requested_paths": ["src/apf/example.py"],
            "scope_digest": "sha256:" + "a" * 64,
        },
        "acknowledged_items": sorted(REQUIRED_ACKNOWLEDGEMENTS),
        "nonce": str(uuid4()),
    }
    assert client.post(
        "/v1/console/reference-material-consents", json=payload
    ).status_code == 403
    recorded = client.post(
        "/v1/console/reference-material-consents",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert recorded.status_code == 201
    assert recorded.json()["decision"]["decision"] == "SANDBOX_IMPLEMENTATION_ALLOWED"
    assert recorded.json()["decision"]["merge_allowed"] is False
    assert recorded.json()["decision"]["deployment_allowed"] is False


def test_reference_material_ui_is_owner_only(tmp_path):
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
        reference_consent_store=ReferenceConsentStore(tmp_path),
    )
    client = TestClient(app, base_url="https://testserver")
    client.post(
        "/console/dev/session",
        json={"tenant_id": str(uuid4()), "principal_id": str(uuid4()), "role": "operator"},
    )
    assert client.get("/reference-material-consent").status_code == 403
    assert client.get("/v1/console/reference-material-notice").status_code == 403


def test_console_requires_session_and_has_security_headers():
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
    )
    anonymous = TestClient(app).get("/console")
    assert anonymous.status_code == 401
    client, _, _, _ = make_client()
    response = client.get("/console")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "localStorage" not in response.text
    assert "sessionStorage" not in response.text


def test_cookie_flags_and_tenant_scoped_targets():
    client, repository, tenant_id, _ = make_client()
    repository.create_target(target_payload(tenant_id, "<img src=x onerror=alert(1)>") )
    repository.create_target(target_payload(uuid4(), "다른 임차인 비밀"))
    response = client.get("/v1/console/targets")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "<img src=x onerror=alert(1)>"
    session = client.cookies.get(SESSION_COOKIE)
    assert session and "다른 임차인 비밀" not in response.text
    login_headers = client.post(
        "/console/dev/session",
        json={"tenant_id": str(tenant_id), "principal_id": str(uuid4()), "role": "operator"},
    ).headers.get_list("set-cookie")
    assert any("HttpOnly" in value and "Secure" in value and "SameSite=strict" in value for value in login_headers)


def test_tampered_session_is_rejected():
    client, _, _, _ = make_client()
    client.cookies.set(SESSION_COOKIE, client.cookies.get(SESSION_COOKIE) + "0")
    assert client.get("/v1/console/summary").status_code == 401


def test_review_submission_requires_csrf_and_reviewer_and_store():
    task_id = uuid4()
    payload = {
        "task_fingerprint": "sha256:" + "a" * 64, "task_id": str(task_id),
        "job_id": str(uuid4()), "request_fingerprint": "sha256:" + "b" * 64,
        "tenant_id": str(uuid4()), "principal_id": str(uuid4()), "stage": "RIGHTS",
        "evidence_fingerprint": "sha256:" + "c" * 64, "decision": "APPROVE",
        "expires_at": "2031-01-01T01:00:00+00:00", "nonce": str(uuid4()),
        "signature": "d" * 128,
    }
    operator, _, _, csrf = make_client(role="operator")
    assert operator.post(
        f"/v1/console/reviews/{task_id}/decisions", json=payload,
        headers={"X-CSRF-Token": csrf},
    ).status_code == 403
    reviewer, _, _, csrf = make_client(role="reviewer")
    assert reviewer.post(f"/v1/console/reviews/{task_id}/decisions", json=payload).status_code == 403
    unavailable = reviewer.post(
        f"/v1/console/reviews/{task_id}/decisions", json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert unavailable.status_code in {403, 503}
    assert reviewer.get("/v1/console/reviews").status_code == 503


def test_production_console_fails_closed_without_secret():
    with pytest.raises(RuntimeError, match="APF_CONSOLE_SESSION_SECRET"):
        ConsoleSecurity(environment="production", secret=None)


def test_dev_session_is_explicitly_disabled_by_default():
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(environment="development", secret="s" * 32),
    )
    response = TestClient(app).post(
        "/console/dev/session",
        json={"tenant_id": str(uuid4()), "principal_id": str(uuid4()), "role": "operator"},
    )
    assert response.status_code == 404


def test_summary_exposes_no_secret_or_raw_material():
    client, _, _, _ = make_client()
    body = client.get("/v1/console/summary").text.lower()
    for forbidden in ("password", "authorization", "cookie", "raw_material", "session"):
        assert forbidden not in body


def test_inbox_stage_cannot_traverse_outside_mailbox():
    client, _, _, _ = make_client()
    response = client.get("/v1/console/inbox", params={"stage": "../state"})
    assert response.status_code == 422


def test_co_creation_session_requires_exact_owner_and_safe_id(tmp_path, monkeypatch):
    monkeypatch.setattr(console_module, "__file__", str(tmp_path / "src/apf/console.py"))
    client, _, tenant_id, _ = make_client()
    principal_id = uuid4()
    session_id = uuid4()
    sessions = tmp_path / "state/co-creation/sessions"
    sessions.mkdir(parents=True)
    path = sessions / f"{session_id}.json"
    path.write_text(
        json.dumps({
            "tenant_id": str(tenant_id), "principal_id": str(principal_id), "secret": "private"
        }), encoding="utf-8"
    )
    endpoint = f"/v1/console/co-creation/sessions/{session_id}"
    assert client.get(endpoint).status_code == 404
    assert client.get("/v1/console/co-creation/sessions/not-a-uuid").status_code == 404
    client.post("/console/dev/session", json={
        "tenant_id": str(tenant_id), "principal_id": str(principal_id), "role": "operator"
    })
    assert client.get(endpoint).json()["secret"] == "private"
def test_plain_approval_routes_require_owner_csrf_and_store(tmp_path):
    operator, _, _, _ = make_client(
        role="operator", approval_store=PlainLanguageApprovalStore(tmp_path)
    )
    assert operator.get("/v1/console/self-improvement-reports").status_code == 403

    owner, _, _, csrf = make_client(
        role="owner", approval_store=PlainLanguageApprovalStore(tmp_path)
    )
    assert owner.get("/v1/console/self-improvement-reports").status_code == 200
    payload = {
        "decision": "APPROVE", "scope_digest": "a" * 64,
        "nonce": str(uuid4()), "expires_at": "2031-01-01T01:00:00+00:00",
    }
    request_id = "missing"
    assert owner.post(
        f"/v1/console/self-improvement-reports/{request_id}/decision", json=payload
    ).status_code == 403
    response = owner.post(
        f"/v1/console/self-improvement-reports/{request_id}/decision", json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_visual_platform_dialogue_api_separates_owner_and_arkaon_operator(tmp_path):
    tenant_id, owner_id, operator_id = uuid4(), uuid4(), uuid4()
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
        visual_dialogue_store=VisualPlatformDialogueStore(tmp_path),
    )
    client = TestClient(app, base_url="https://testserver")

    owner_session = client.post(
        "/console/dev/session",
        json={"tenant_id": str(tenant_id), "principal_id": str(owner_id), "role": "owner"},
    )
    owner_csrf = owner_session.json()["csrf_token"]
    created = client.post(
        "/v1/console/platform-dialogues",
        headers={"X-CSRF-Token": owner_csrf},
        json={
            "name": "부업장터", "purpose": "벌거리 연결", "audience": ["참여자"],
            "required_capabilities": ["탐색", "정산"], "constraints": ["모바일 우선"],
        },
    )
    assert created.status_code == 201
    dialogue_id = created.json()["dialogue_id"]
    assert client.post(
        f"/v1/console/platform-dialogues/{dialogue_id}/revisions",
        headers={"X-CSRF-Token": owner_csrf},
        json={
            "based_on_revision_digest": None, "change_summary": "첫 화면",
            "screens": [{
                "screen_id": "home", "title": "홈", "purpose": "탐색",
                "components": ["검색", "추천"],
            }],
        },
    ).status_code == 403

    operator_session = client.post(
        "/console/dev/session",
        json={"tenant_id": str(tenant_id), "principal_id": str(operator_id), "role": "operator"},
    )
    operator_csrf = operator_session.json()["csrf_token"]
    revised = client.post(
        f"/v1/console/platform-dialogues/{dialogue_id}/revisions",
        headers={"X-CSRF-Token": operator_csrf},
        json={
            "based_on_revision_digest": None, "change_summary": "첫 화면",
            "screens": [{
                "screen_id": "home", "title": "홈", "purpose": "탐색",
                "components": ["검색", "추천"],
            }],
        },
    )
    assert revised.status_code == 200
    image = client.get(
        f"/v1/console/platform-dialogues/{dialogue_id}/revisions/1/preview.svg"
    )
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/svg+xml")
