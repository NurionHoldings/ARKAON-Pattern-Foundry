from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import SESSION_COOKIE, ConsoleSecurity
from apf.domain import AnalysisTargetCreate
from apf.plain_language_approval import PlainLanguageApprovalStore
from apf.repository import MemoryRepository


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
