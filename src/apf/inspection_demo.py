"""Isolated, synthetic product walkthrough. Never issues a console principal."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from .business_card import BusinessCardRequest, _back, _front
from .logo_draft import LogoDraftRequest, _svg

COOKIE = "apf_inspection_demo"
PRICES_KRW = {"logo": 50_000, "card": 10_000}
STEPS = (
    ("요청 미리보기", "예시 요청의 목적과 필요한 결과물을 확인합니다."),
    ("결과물 미리보기", "예시 화면의 구성과 수령 형태를 확인합니다."),
)


def _preview_svg(svg: str) -> str:
    """Return only a marked preview; never expose an unmarked artifact in this flow."""
    card = 'viewBox="0 0 1050 600"' in svg
    cx, cy, x, y, size = (525, 300, 215, 315, 68) if card else (360, 90, 170, 105, 42)
    overlay = (f'<g opacity=".28" transform="rotate(-20 {cx} {cy})">'
               f'<text x="{x}" y="{y}" font-family="Arial" font-size="{size}" '
               'font-weight="700" fill="#27334c">미리보기 · PREVIEW</text></g>')
    return svg.replace("</svg>", overlay + "</svg>")


def _image(svg: str, label: str) -> str:
    encoded = base64.b64encode(_preview_svg(svg).encode()).decode("ascii")
    return f'<figure><img alt="{label}" src="data:image/svg+xml;base64,{encoded}"><figcaption>{label}</figcaption></figure>'


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
            '<p>간단한 로고·명함은 입력에 맞춰 시안을 실제 생성합니다. 파일 수령은 로그인과 결제 후 가능합니다.</p>'
            '<ol>' + steps + '</ol>'
            '<p><a href="/inspection/make">로고·명함 시안 만들기</a></p>'
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
            '<p>템플릿·플랫폼 제작에 참여하려면 회원가입 또는 로그인이 필요합니다.</p>'
            '<p>제작 계약 및 결과물 수령 단계에서는 별도 결제 절차를 안내합니다.</p>'
            '<p>현재 체험 계정에서는 진행할 수 없습니다. 회원가입·결제 연동이 준비되면 '
            '운영 화면에서 안내합니다.</p><a href="/inspection/preview">미리보기로 돌아가기</a></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; base-uri 'none'"},
        )

    @app.get("/inspection/make", response_class=HTMLResponse)
    def inspection_make(request: Request) -> HTMLResponse:
        authorized(request)
        return HTMLResponse(
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>로고·명함 체험 제작</title><style>'
            'body{font:16px/1.5 system-ui;background:#f4f6fb;padding:20px}'
            'main{max-width:540px;margin:auto;background:white;padding:24px;border-radius:14px}'
            'label,input,select,button{display:block;width:100%;box-sizing:border-box;margin:12px 0}'
            'input,select,button{font:inherit;padding:10px;border:1px solid #b3bfd1;border-radius:8px}'
            'button{background:#173a79;color:white}</style><main><h1>간단한 시안 제작</h1>'
            '<p>입력에 따라 벡터 로고와 명함 앞·뒷면을 만듭니다. 파일은 아직 제공하지 않습니다.</p>'
            '<form method="post" action="/inspection/make">'
            '<label>제작 항목<select name="product" required>'
            '<option value="logo">로고 · 50,000원</option>'
            '<option value="card">명함 · 10,000원</option>'
            '<option value="both">로고 + 명함 · 60,000원</option></select></label>'
            '<label>브랜드명<input name="brand" required maxlength="64"></label>'
            '<label>한 줄 소개<input name="tagline" required maxlength="100"></label>'
            '<label>색상<input name="color" type="color" value="#2563eb"></label>'
            '<label>도형<select name="shape"><option value="orbit">원</option>'
            '<option value="arch">아치</option><option value="spark">별</option></select></label>'
            '<p>명함을 선택한 경우 아래 네 항목도 입력하세요.</p>'
            '<label>명함 이름<input name="name" maxlength="80"></label>'
            '<label>직함<input name="title" maxlength="100"></label>'
            '<label>전화<input name="phone" maxlength="80"></label>'
            '<label>이메일<input name="email" type="email" maxlength="160"></label>'
            '<button type="submit">로고·명함 시안 생성</button></form></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"},
        )

    @app.post("/inspection/make", response_class=HTMLResponse)
    async def inspection_make_preview(request: Request) -> HTMLResponse:
        authorized(request)
        body = await request.body()
        if len(body) > 4096:
            raise HTTPException(status_code=413, detail="input too large")
        values = parse_qs(body.decode("utf-8", errors="replace"))
        product = values.get("product", [""])[0]
        if product not in {"logo", "card", "both"}:
            raise HTTPException(status_code=422, detail="invalid product selection")
        data = {key: values.get(key, [""])[0] for key in
                ("brand", "tagline", "color", "shape", "name", "title", "phone", "email")}
        try:
            logo = LogoDraftRequest(name=data["brand"], tagline=data["tagline"],
                                    color=data["color"], shape=data["shape"])
            if product in {"card", "both"}:
                BusinessCardRequest(logo_draft_id="inspection", name=data["name"],
                                    title=data["title"], phone=data["phone"],
                                    email=data["email"], brand_text=data["brand"])
        except ValidationError:
            raise HTTPException(status_code=422, detail="invalid preview input") from None
        logo_svg = _svg(logo.name, logo.tagline, logo.color, logo.shape, 1)
        pictures = ""
        if product in {"logo", "both"}:
            pictures += _image(logo_svg, "로고 미리보기")
        if product in {"card", "both"}:
            pictures += _image(_front(logo_svg, data["name"], data["title"], data["phone"],
                                      data["email"], data["brand"]), "명함 앞면 미리보기")
            pictures += _image(_back(logo_svg, data["brand"]), "명함 뒷면 미리보기")
        # Signed form carries only the kind, never the contact fields or a clean SVG.
        _, secret = configured()
        issued = int(time.time())
        invoice_data = json.dumps({"product": product, "issued": issued}, separators=(",", ":"))
        token = base64.urlsafe_b64encode(invoice_data.encode()).decode().rstrip("=")
        signature = hmac.new(secret, b"invoice:" + token.encode(), hashlib.sha256).hexdigest()
        invoice_form = "".join(
            f'<form method="post" action="/inspection/invoice">'
            f'<input type="hidden" name="ticket" value="{token}.{signature}">'
            f'<input type="hidden" name="requested" value="{action}">'
            f'<button type="submit">{label}</button></form>'
            for action, label in (("print", "출력"), ("download", "다운로드"))
        )
        return HTMLResponse(
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>생성된 시안 미리보기</title><style>'
            'body{font:16px/1.5 system-ui;background:#f4f6fb;padding:16px}'
            'main{max-width:760px;margin:auto}figure{background:white;padding:12px;border-radius:12px}'
            'img{width:100%;height:auto}button{font:inherit;padding:12px;background:#173a79;'
            'color:white;border:0;border-radius:9px}</style>'
            '<main><h1>실제 생성된 시안 · 미리보기</h1>'
            '<p>선택한 SVG 시안을 입력값으로 생성했습니다. 미리보기 표시가 포함됩니다.</p>'
            + pictures
            + invoice_form + '<a href="/inspection/make">다시 만들기</a></main>',
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                     "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"},
        )

    @app.post("/inspection/invoice", response_class=HTMLResponse)
    async def inspection_invoice(request: Request) -> HTMLResponse:
        authorized(request)
        body = await request.body()
        if len(body) > 512:
            raise HTTPException(status_code=413, detail="input too large")
        ticket = parse_qs(body.decode("utf-8", errors="replace")).get("ticket", [""])[0]
        requested = parse_qs(body.decode("utf-8", errors="replace")).get("requested", [""])[0]
        if requested not in {"print", "download"}:
            raise HTTPException(status_code=422, detail="invalid delivery action")
        try:
            token, signature = ticket.split(".", 1)
            _, secret = configured()
            expected = hmac.new(secret, b"invoice:" + token.encode(), hashlib.sha256).hexdigest()
            details = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
            if (not hmac.compare_digest(signature, expected)
                    or details["product"] not in {"logo", "card", "both"}
                    or not isinstance(details["issued"], int)
                    or not 0 <= time.time() - details["issued"] < 1800):
                raise ValueError
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=403, detail="invalid invoice request") from None
        product = details["product"]
        selected = ("logo", "card") if product == "both" else (product,)
        items = "".join(
            f'<li>{"로고" if item == "logo" else "명함"}: {PRICES_KRW[item]:,}원</li>'
            for item in selected
        )
        amount = sum(PRICES_KRW[item] for item in selected)
        invoice_id = hashlib.sha256(ticket.encode()).hexdigest()[:16].upper()
        return HTMLResponse(
            '<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>결제청구서 초안</title><main><h1>결제청구서 초안</h1>'
            f'<p>참조번호: {invoice_id}</p><p>발행일: {datetime.now(UTC).date()}</p>'
            f'<p>제작 항목</p><ul>{items}</ul>'
            f'<p>요청한 기능: {"출력" if requested == "print" else "다운로드"}</p>'
            f'<p>표시 합계: {amount:,}원</p>'
            '<p>부가세 포함 여부와 최종 결제 조건은 주문 단계에서 확정합니다.</p>'
            '<p>출력·다운로드 및 실제 제작 참여에는 회원가입 또는 로그인 후 결제가 필요합니다.</p>'
            '<p>이 문서는 결제 안내용 초안이며 결제 승인, 세금계산서 또는 확정 청구가 아닙니다.</p>'
            '<a href="/inspection/make">체험으로 돌아가기</a></main>',
            headers={"Cache-Control": "no-store", "Content-Security-Policy":
                     "default-src 'none'; base-uri 'none'"},
        )
