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
    ("요청", "필요한 결과물과 목적을 입력합니다."),
    ("구성 확인", "아르카온이 작업 단계를 제안하고 사용자가 범위를 확인합니다."),
    ("시안 검토", "로고·명함·웹 화면의 시안을 비교하고 수정합니다."),
    ("승인", "선택한 시안과 적용 범위를 확인하고 승인합니다."),
    ("수령", "완성 파일을 내려받고 인쇄 또는 배포 결과를 확인합니다."),
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
            '<title>ARKAON 제작 단계</title><style>'
            'body{font:16px/1.55 system-ui;background:#f4f6fb;color:#162544;margin:0;padding:20px}'
            'main{max-width:720px;margin:auto}li{background:white;margin:12px 0;padding:16px;'
            'border-radius:12px}p{margin:6px 0}a{color:#174583}'
            '</style><main><h1>요청부터 결과물 수령까지</h1>'
            '<p>이 화면은 예시 작업 흐름입니다. 실제 제작·결제·배포를 실행하지 않습니다.</p>'
            '<ol>' + steps + '</ol><a href="/inspection">체험 시작 화면</a></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"},
        )
