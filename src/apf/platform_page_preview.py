"""Scriptless home/detail page mockups derived from an approved dialogue revision."""

from __future__ import annotations

from html import escape
from typing import Literal

from .preview_design import FOUNDATION_CSS, PLATFORM_CSS

PageKind = Literal["home", "detail"]


def render_page_mockup(brief: dict[str, object], screens: list[dict[str, object]], kind: PageKind) -> str:
    if kind not in {"home", "detail"}:
        raise ValueError("PLATFORM_PREVIEW_KIND_INVALID")
    if not screens:
        raise ValueError("PLATFORM_PREVIEW_SCREENS_REQUIRED")
    home = next(
        (screen for screen in screens if str(screen["screen_id"]).lower() == "home"), screens[0]
    )
    detail = next(
        (screen for screen in screens if str(screen["screen_id"]).lower() == "detail"
         and screen is not home),
        next((screen for screen in screens if screen is not home), None),
    )
    chosen = home if kind == "home" else detail
    brand = escape(str(brief["name"]))
    purpose = escape(str(brief["purpose"]))
    title = escape(str(chosen["title"])) if chosen else "상세 화면 명세가 필요합니다"
    summary = escape(str(chosen["purpose"])) if chosen else (
        "두 번째 화면의 이름·목적·구성요소를 설계 버전에 추가하면 상세 화면이 나타납니다."
    )
    components = [escape(str(item)) for item in chosen["components"]] if chosen else []
    cards = "".join(
        f'<article class="feature"><span class="number">{index:02d} / COMPONENT</span>'
        f'<h2>{item}</h2><p>기능 연결 전 구성요소 시안입니다.</p></article>'
        for index, item in enumerate(components[:8], 1)
    )
    if not cards:
        cards = '<p class="empty">이 화면의 구성요소가 아직 정의되지 않았습니다.</p>'
    if kind == "home":
        body = (
            '<section class="preview-hero" aria-label="홈 첫 화면">'
            f'<div class="preview-hero-copy"><span class="eyebrow">HOME / 01</span>'
            f'<h1>{title}</h1><p>{summary}</p><span class="action">시작하기 · 시안</span></div>'
            '<div class="hero-graphic" aria-hidden="true"><span></span></div></section>'
            f'<p class="section-label">SCREEN COMPONENTS / 핵심 구성</p>'
            f'<section class="features" aria-label="홈 화면 구성요소">{cards}</section>'
        )
    else:
        body = (
            f'<nav class="crumb" aria-label="현재 위치">{brand} / 상세 시안</nav>'
            '<section class="detail-stage" aria-label="상세 첫 화면">'
            '<div class="detail-visual" aria-label="콘텐츠 이미지 자리">'
            '<span>콘텐츠 이미지 자리 · 제작 시 교체</span></div>'
            f'<div class="detail-copy"><span class="eyebrow">DETAIL / 02</span>'
            f'<h1>{title}</h1><p>{summary}</p>'
            '<div class="detail-meta">목적과 구성요소 확인 · 기능 연결 전</div>'
            '<span class="action">다음 단계 · 시안</span></div></section>'
            '<p class="section-label">SCREEN COMPONENTS / 상세 구성</p>'
            f'<section class="features" aria-label="상세 화면 구성요소">{cards}</section>'
        )
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{brand} · {title}</title>
<style>{FOUNDATION_CSS}{PLATFORM_CSS}</style></head>
<body><header class="preview-header"><div class="wrap">
<span class="preview-brand">{brand}</span>
<nav class="preview-nav" aria-label="시안 메뉴"><span>홈</span><span>소개</span><span>상세</span></nav>
</div></header><main class="wrap preview-main">{body}</main>
<footer class="preview-footer"><div class="wrap">{purpose} · 화면 시안 / 기능 연결 전</div></footer>
</body></html>"""
