"""Isolated, synthetic product walkthrough. Never issues a console principal."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

COOKIE = "apf_inspection_demo"
STEPS = (
    ("요청 미리보기", "예시 요청의 목적과 필요한 결과물을 확인합니다."),
    ("결과물 미리보기", "예시 화면의 구성과 수령 형태를 확인합니다."),
)


def install_inspection_demo(app: FastAPI) -> None:
    def configured() -> tuple[str, bytes]:
        demo_id = os.getenv("APF_DEMO_INSPECTION_ID", "")
        secret = os.getenv("APF_DEMO_SESSION_SECRET", "").encode()
        if not demo_id or len(secret) < 32:
            raise HTTPException(status_code=404, detail="demo unavailable")
        return demo_id, secret

    def authorized(request: Request) -> None:
        _, secret = configured()
        token = request.cookies.get(COOKIE, "")
        try:
            expiry_text, signature = token.split(".", 1)
            expiry = int(expiry_text)
            expected = hmac.new(secret, f"inspection:{expiry}".encode(), hashlib.sha256).hexdigest()
            if expiry <= time.time() or not hmac.compare_digest(signature, expected):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=401, detail="demo sign-in required") from None

    @app.get("/inspection", response_class=HTMLResponse)
    def inspection_sign_in() -> HTMLResponse:
        configured()
        return HTMLResponse(
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>ARKAON 구현 흐름 체험</title><style>'
            'body{font:16px/1.5 system-ui;background:#f4f6fb;color:#162544;margin:0;padding:24px}'
            'main{max-width:440px;margin:8vh auto;background:white;padding:28px;border-radius:18px}'
            'label,input,button{display:block;width:100%;box-sizing:border-box;margin:12px 0}'
            'input,button{font:inherit;padding:12px;border:1px solid #a6b5d0;border-radius:9px}'
            'button{background:#173a79;color:white;cursor:pointer}</style>'
            '<main><h1>구현 흐름 체험</h1><p>검증용 아이디와 숫자 4자리를 입력하세요.</p>'
            '<form method="post" action="/inspection/sign-in">'
            '<label>아이디<input name="username" required autocomplete="username"></label>'
            '<label>체험용 숫자 4자리<input name="pin" type="password" inputmode="numeric"'
            ' pattern="[0-9]{4}" minlength="4" maxlength="4" required autocomplete="off"></label>'
            '<button type="submit">구현 흐름 보기</button></form>'
            '<p>체험은 예시 데이터만 사용합니다. 운영 계정·고객 데이터와 연결되지 않습니다.</p></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"},
        )

    @app.post("/inspection/sign-in")
    async def inspection_session(request: Request) -> RedirectResponse:
        demo_id, secret = configured()
        if int(request.headers.get("content-length", "0")) > 512:
            raise HTTPException(status_code=413, detail="input too large")
        values = parse_qs((await request.body()).decode("utf-8", errors="replace"))
        username, pin = values.get("username", [""])[0], values.get("pin", [""])[0]
        if not hmac.compare_digest(username, demo_id) or not re.fullmatch(r"[0-9]{4}", pin):
            raise HTTPException(status_code=401, detail="invalid demo credentials")
        expiry = int(time.time()) + 1800
        signature = hmac.new(secret, f"inspection:{expiry}".encode(), hashlib.sha256).hexdigest()
        response = RedirectResponse("/inspection/workflow", status_code=303)
        response.set_cookie(COOKIE, f"{expiry}.{signature}", max_age=1800, httponly=True,
                            secure=True, samesite="strict", path="/inspection")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/inspection/workflow", response_class=HTMLResponse)
    def inspection_workflow(request: Request) -> HTMLResponse:
        authorized(request)
        steps = "".join(
            f'<li><strong>{title}</strong><p>{description}</p></li>' for title, description in STEPS
        )
        return HTMLResponse(
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>ARKAON 요청·결과물 미리보기</title><style>'
            'body{font:16px/1.55 system-ui;background:#f4f6fb;color:#162544;margin:0;padding:20px}'
            'main{max-width:720px;margin:auto}li{background:white;margin:12px 0;padding:16px;'
            'border-radius:12px}p{margin:6px 0}a{color:#174583}'
            '</style><main><h1>요청과 결과물 미리보기</h1>'
            '<p>체험 계정은 예시 요청과 결과물만 볼 수 있습니다. 실제 데이터와 연결되지 않습니다.</p>'
            '<ol>' + steps + '</ol>'
            '<p><a href="/inspection/preview">요청·결과물 미리보기 열기</a></p>'
            '<p><a href="/inspection/participate">직접 제작에 참여하려면</a></p></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"},
        )

    @app.get("/inspection/preview", response_class=HTMLResponse)
    def inspection_preview(request: Request) -> HTMLResponse:
        authorized(request)
        return HTMLResponse(
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>요청과 결과물 미리보기</title><style>'
            'body{font:16px/1.6 system-ui;background:#f4f6fb;color:#162544;padding:18px}'
            'main{max-width:680px;margin:auto}section{background:white;border-radius:14px;'
            'padding:20px;margin:16px 0}a{color:#174583}'
            '.samples{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}'
            '.sample{border:1px solid #d6dfeb;border-radius:12px;padding:16px;min-height:120px}'
            '.brand{font-size:1.5rem;font-weight:800;color:#174583}.sample small{display:block}'
            '</style><main><h1>미리보기 전용</h1>'
            '<section><h2>요청 예시</h2><p>목적: 소규모 사업 소개</p>'
            '<p>필요한 구성: 로고, 모바일 명함, 소개 페이지</p>'
            '<p>입력과 수정은 이 화면에서 할 수 없습니다.</p></section>'
            '<section><h2>결과물 예시</h2><div class="samples">'
            '<div class="sample"><small>로고 시안</small><p class="brand">가온 · STUDIO</p></div>'
            '<div class="sample"><small>모바일 명함</small><p class="brand">가온</p>'
            '<p>김가온 · 대표<br>연락처는 예시에서 제외</p></div>'
            '<div class="sample"><small>소개 페이지 화면</small><h3>당신의 일을 소개합니다</h3>'
            '<p>서비스 · 작업 사례 · 문의</p></div></div>'
            '<p>실제 고객 파일이 아닌 설명용 미리보기입니다. 파일 다운로드·인쇄·배포는 제공하지 않습니다.</p>'
            '</section><a href="/inspection/participate">직접 제작에 참여하려면</a></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"},
        )

    @app.get("/inspection/participate", response_class=HTMLResponse)
    def inspection_participation_notice(request: Request) -> HTMLResponse:
        authorized(request)
        return HTMLResponse(
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>실제 제작 참여 안내</title><main><h1>실제 제작 참여 안내</h1>'
            '<p>요청 제출, 시안 수정·승인, 제작 실행 및 결과물 수령에는 '
            '회원가입 또는 로그인 후 결제 절차가 필요합니다.</p>'
            '<p>현재 체험 계정에서는 진행할 수 없습니다. 회원가입·결제 연동이 준비되면 '
            '운영 화면에서 안내합니다.</p><a href="/inspection/preview">미리보기로 돌아가기</a></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; base-uri 'none'"},
        )
