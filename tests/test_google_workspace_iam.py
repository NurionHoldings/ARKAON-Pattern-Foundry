import json
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi.testclient import TestClient

import apf.google_workspace_iam as google_iam
from apf.api import create_app
from apf.console import SESSION_COOKIE, ConsoleSecurity
from apf.repository import MemoryRepository


def configure_google(monkeypatch):
    tenant_id, principal_id = uuid4(), uuid4()
    monkeypatch.setenv("APF_ENV", "test")
    monkeypatch.setenv("APF_GOOGLE_OIDC_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("APF_GOOGLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("APF_CONSOLE_PUBLIC_ORIGIN", "https://arkaonfoundry.netlify.app")
    monkeypatch.setenv("APF_GOOGLE_WORKSPACE_DOMAINS", "example.org")
    monkeypatch.setenv(
        "APF_IAM_PRINCIPAL_MAP_JSON",
        json.dumps(
            {
                "operator@example.org": {
                    "tenant_id": str(tenant_id),
                    "principal_id": str(principal_id),
                    "role": "operator",
                }
            }
        ),
    )
    return tenant_id, principal_id


def make_client():
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(
            environment="test", secret="s" * 32, allow_dev_sessions=True
        ),
    )
    return app, TestClient(app, base_url="https://arkaonfoundry.netlify.app")


def test_google_login_uses_state_nonce_pkce_and_secure_transaction_cookie(monkeypatch):
    configure_google(monkeypatch)
    _, client = make_client()
    response = client.get("/console/auth/login", follow_redirects=False)
    assert response.status_code == 302

    location = urlsplit(response.headers["location"])
    query = parse_qs(location.query)
    assert location.netloc == "accounts.google.com"
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid email"]
    assert query["hd"] == ["example.org"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["state"][0]) >= 32
    assert len(query["nonce"][0]) >= 32
    assert len(query["code_challenge"][0]) == 43
    cookie = next(
        value for value in response.headers.get_list("set-cookie")
        if value.startswith("apf_google_oauth_tx=")
    )
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Max-Age=600" in cookie


def test_google_callback_validates_iam_and_issues_server_mapped_session(monkeypatch):
    tenant_id, principal_id = configure_google(monkeypatch)
    app, client = make_client()
    start = client.get("/console/auth/login", follow_redirects=False)
    query = parse_qs(urlsplit(start.headers["location"]).query)
    nonce = query["nonce"][0]

    class TokenResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id_token": "signed-id-token"}

    monkeypatch.setattr(google_iam.requests, "post", lambda *args, **kwargs: TokenResponse())
    monkeypatch.setattr(
        google_iam.id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "iss": "https://accounts.google.com",
            "aud": audience,
            "nonce": nonce,
            "email": "operator@example.org",
            "email_verified": True,
            "hd": "example.org",
            "sub": "google-user-subject",
        },
    )

    response = client.get(
        "/console/auth/callback?code=one-time-code&state=" + query["state"][0],
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert 'href="https://arkaonfoundry.netlify.app/console"' in response.text
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.get_list("set-cookie")
    session = next(value for value in cookies if value.startswith("apf_console_session="))
    csrf = next(value for value in cookies if value.startswith("apf_console_csrf="))
    assert "HttpOnly" in session and "Secure" in session and "SameSite=strict" in session
    assert "Secure" in csrf and "SameSite=strict" in csrf
    actor = app.state.console_security.verify(client.cookies.get(SESSION_COOKIE))
    assert actor.tenant_id == tenant_id
    assert actor.principal_id == principal_id
    assert actor.role == "operator"
    assert client.get("/console").status_code == 200
    principal = client.get("/v1/console/predeployment")
    assert principal.status_code == 200


def test_google_callback_rejects_bad_state_and_unlisted_identity(monkeypatch):
    configure_google(monkeypatch)
    _, client = make_client()
    start = client.get("/console/auth/login", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    bad_state = client.get(
        "/console/auth/callback?code=one-time-code&state=attacker-value",
        follow_redirects=False,
    )
    assert bad_state.status_code == 400

    class TokenResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id_token": "signed-id-token"}

    monkeypatch.setattr(google_iam.requests, "post", lambda *args, **kwargs: TokenResponse())
    monkeypatch.setattr(
        google_iam.id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "iss": "https://accounts.google.com",
            "aud": audience,
            "nonce": parse_qs(urlsplit(start.headers["location"]).query)["nonce"][0],
            "email": "someone-else@example.org",
            "email_verified": True,
            "hd": "example.org",
            "sub": "unlisted-subject",
        },
    )
    denied = client.get(
        "/console/auth/callback?code=one-time-code&state=" + state,
        follow_redirects=False,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "account is not authorized"


def test_google_login_fails_closed_when_not_configured(monkeypatch):
    for key in (
        "APF_GOOGLE_OIDC_CLIENT_ID",
        "APF_GOOGLE_OIDC_CLIENT_SECRET",
        "APF_CONSOLE_PUBLIC_ORIGIN",
        "APF_GOOGLE_WORKSPACE_DOMAINS",
        "APF_IAM_PRINCIPAL_MAP_JSON",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APF_ENV", "test")
    _, client = make_client()
    assert client.get("/console/auth/login").status_code == 503


def test_production_blocks_unauthenticated_target_api_and_openapi(monkeypatch):
    monkeypatch.setenv("APF_ENV", "production")
    app = create_app(
        repository=MemoryRepository(),
        console_security=ConsoleSecurity(environment="production", secret="s" * 32),
        console_review_store=object(),
    )
    client = TestClient(app, base_url="https://api.example.test")
    assert client.get("/v1/targets").status_code == 404
    assert client.post("/v1/targets", json={}).status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_console_file_reads_follow_configured_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("APF_ENV", "test")
    monkeypatch.setenv("APF_FOUNDRY_ROOT", str(tmp_path))
    _, client = make_client()
    session = client.post(
        "/console/dev/session",
        json={"tenant_id": str(uuid4()), "principal_id": str(uuid4()), "role": "auditor"},
    )
    assert session.status_code == 200
    response = client.get("/v1/console/predeployment")
    assert response.status_code == 200
    assert response.json() == {"overall": "UNKNOWN", "reports": []}
