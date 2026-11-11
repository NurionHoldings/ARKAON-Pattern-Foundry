"""Optional, server-configured operator password bridge to Foundry sessions."""
import hashlib
import hmac
import os
import secrets
import time
from collections import deque
from threading import Lock
from typing import Annotated
from uuid import UUID

from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


class LoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=512)


def install_operator_login(application, security, principal, csrf_guard):
    from .console import CSRF_COOKIE, SESSION_COOKIE, ConsolePrincipal

    attempts = deque()
    lock = Lock()

    def configured_actor():
        try:
            return ConsolePrincipal(
                tenant_id=UUID(os.environ['APF_OPERATOR_TENANT_ID']),
                principal_id=UUID(os.environ['APF_OPERATOR_PRINCIPAL_ID']),
                role='operator',
            )
        except (KeyError, ValueError):
            raise HTTPException(503, 'operator login is not configured') from None

    def guard_actor(actor):
        if actor.role not in {'owner', 'operator'}:
            raise HTTPException(403, 'operator role required')
        tenant = os.getenv('APF_OPERATOR_TENANT_ID')
        if tenant and str(actor.tenant_id) != tenant:
            raise HTTPException(403, 'operator tenant required')
        return actor

    @application.get('/console/login', response_class=HTMLResponse, include_in_schema=False)
    def login_page(response: Response):
        configured_actor()
        if not os.getenv('APF_OPERATOR_PASSWORD_HASH'):
            raise HTTPException(503, 'operator login is not configured')
        html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>아르카온 운영자 로그인</title><style>body{background:#e4e9df;color:#14332e;font:16px/1.8 system-ui;margin:0}main{max-width:420px;margin:12vh auto;padding:28px;background:#fffdf8;border-radius:12px}input,button{box-sizing:border-box;font:inherit;padding:12px;width:100%;margin:8px 0}button{background:#194e4a;color:white;border:0}a{color:#194e4a}</style><main><h1>운영자 로그인</h1><form id="login"><label>비밀번호<input id="password" type="password" autocomplete="current-password" required maxlength="512"></label><button>로그인</button></form><p id="status" role="status"></p></main><script>document.getElementById('login').addEventListener('submit',async e=>{e.preventDefault();const p=document.getElementById('password');const s=document.getElementById('status');const csrf=document.cookie.split('; ').find(x=>x.startsWith('apf_console_csrf='))?.split('=')[1];try{const r=await fetch('/console/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf||''},body:JSON.stringify({password:p.value})});p.value='';if(!r.ok){s.textContent=r.status===429?'잠시 후 다시 시도해 주세요.':'로그인할 수 없습니다. 비밀번호 또는 운영 설정을 확인해 주세요.';return;}location.assign('/console');}catch{s.textContent='서버 연결을 확인해 주세요.';}});</script></html>'''
        result = HTMLResponse(html, headers={
            'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        result.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), secure=True,
                          httponly=False, samesite='strict', max_age=3600)
        return result

    @application.post('/console/login', include_in_schema=False)
    def login(request: Request, payload: LoginInput):
        # Same-origin password submission; CSRF token obtained from the login page.
        csrf = request.cookies.get(CSRF_COOKIE, '')
        if not csrf or not hmac.compare_digest(csrf, request.headers.get('X-CSRF-Token', '')):
            raise HTTPException(403, 'CSRF verification failed')
        actor = configured_actor()
        now = time.monotonic()
        with lock:
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= 5:
                raise HTTPException(429, 'try again later', headers={'Retry-After': '60'})
            attempts.append(now)
        try:
            scheme, salt, expected = os.environ['APF_OPERATOR_PASSWORD_HASH'].split('$')
            if scheme != 'scrypt' or len(bytes.fromhex(salt)) < 16 or len(bytes.fromhex(expected)) != 64:
                raise ValueError
            actual = hashlib.scrypt(payload.password.encode(), salt=bytes.fromhex(salt),
                                    n=16384, r=8, p=1).hex()
        except (KeyError, ValueError):
            raise HTTPException(503, 'operator login is not configured') from None
        if not hmac.compare_digest(actual, expected):
            raise HTTPException(401, 'invalid credentials')
        result = Response(status_code=204, headers={'Cache-Control': 'no-store'})
        result.set_cookie(SESSION_COOKIE, security.issue(actor), secure=True,
                          httponly=True, samesite='strict', max_age=3600)
        result.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), secure=True,
                          httponly=False, samesite='strict', max_age=3600)
        return result

    from fastapi import Depends

    @application.get('/v1/console/access', include_in_schema=False)
    def access(actor: Annotated[ConsolePrincipal, Depends(principal)]):
        guard_actor(actor)
        return Response(status_code=204, headers={'Cache-Control': 'no-store'})

    @application.post('/console/logout', include_in_schema=False)
    def logout(
        request: Request,
        actor: Annotated[ConsolePrincipal, Depends(principal)],
        verified: Annotated[None, Depends(csrf_guard)],
    ):
        del request, actor, verified
        result = Response(status_code=204, headers={'Cache-Control': 'no-store'})
        result.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite='strict')
        result.delete_cookie(CSRF_COOKIE, secure=True, samesite='strict')
        return result

    return guard_actor
