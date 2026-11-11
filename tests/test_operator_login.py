import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient

from apf.api import create_app
from apf.console import CSRF_COOKIE, SESSION_COOKIE, ConsolePrincipal, ConsoleSecurity
from apf.repository import MemoryRepository


def setup(monkeypatch):
    tenant, operator = uuid4(), uuid4()
    salt = b'0123456789abcdef'
    digest = hashlib.scrypt(b'test-only-password-123', salt=salt, n=16384, r=8, p=1).hex()
    monkeypatch.setenv('APF_OPERATOR_TENANT_ID', str(tenant))
    monkeypatch.setenv('APF_OPERATOR_PRINCIPAL_ID', str(operator))
    monkeypatch.setenv('APF_OPERATOR_PASSWORD_HASH', f'scrypt${salt.hex()}${digest}')
    security = ConsoleSecurity(environment='test', secret='s' * 32)
    app = create_app(repository=MemoryRepository(), console_security=security)
    return TestClient(app, base_url='https://testserver'), security, tenant, operator


def test_password_bridge_issues_existing_session_and_logout(monkeypatch):
    client, security, tenant, operator = setup(monkeypatch)
    assert client.get('/v1/console/access').status_code == 401
    assert client.get('/console/login').status_code == 200
    headers = {'X-CSRF-Token': client.cookies[CSRF_COOKIE]}
    assert client.post('/console/login', json={'password': 'wrong'}, headers=headers).status_code == 401
    response = client.post('/console/login', json={'password': 'test-only-password-123'}, headers=headers)
    assert response.status_code == 204
    assert 'HttpOnly' in response.headers.get_list('set-cookie')[0]
    assert 'Secure' in response.headers.get_list('set-cookie')[0]
    assert security.verify(client.cookies[SESSION_COOKIE]).tenant_id == tenant
    assert security.verify(client.cookies[SESSION_COOKIE]).principal_id == operator
    assert client.get('/v1/console/access').status_code == 204
    assert client.get('/console').status_code == 200
    assert client.post('/console/logout').status_code == 403
    assert client.post('/console/logout', headers={'X-CSRF-Token': client.cookies[CSRF_COOKIE]}).status_code == 204
    assert client.get('/v1/console/access').status_code == 401


def test_role_tenant_expiry_and_anonymous_are_denied(monkeypatch):
    client, security, tenant, operator = setup(monkeypatch)
    for role, tenant_id in [('reviewer', tenant), ('auditor', tenant), ('operator', uuid4())]:
        client.cookies.set(SESSION_COOKIE, security.issue(ConsolePrincipal(tenant_id, operator, role)))
        for url in ['/console', '/v1/console/access', '/v1/console/mailbox']:
            assert client.get(url).status_code == 403
    client.cookies.set(SESSION_COOKIE, 'tampered.signature')
    assert client.get('/v1/console/mailbox').status_code == 401


def test_login_csrf_rate_limit_and_unconfigured_fail_closed(monkeypatch):
    client, _, _, _ = setup(monkeypatch)
    assert client.post('/console/login', json={'password': 'x'}).status_code == 403
    client.get('/console/login')
    headers = {'X-CSRF-Token': client.cookies[CSRF_COOKIE]}
    for _ in range(5):
        assert client.post('/console/login', json={'password': 'wrong'}, headers=headers).status_code == 401
    assert client.post('/console/login', json={'password': 'wrong'}, headers=headers).status_code == 429
    monkeypatch.delenv('APF_OPERATOR_PASSWORD_HASH')
    assert client.get('/console/login').status_code == 503
