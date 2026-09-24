"""Scriptless home/detail page mockups derived from an approved dialogue revision."""

from __future__ import annotations

from html import escape
from typing import Literal

PageKind = Literal["home", "detail"]


def render_page_mockup(brief: dict[str, object], screens: list[dict[str, object]], kind: PageKind) -> str:
    if kind not in {"home", "detail"}:
        raise ValueError("PLATFORM_PREVIEW_KIND_INVALID")
    if not screens:
        raise ValueError("PLATFORM_PREVIEW_SCREENS_REQUIRED")
    chosen = screens[0] if kind == "home" else (screens[1] if len(screens) > 1 else None)
    brand = escape(str(brief["name"]))
    purpose = escape(str(brief["purpose"]))
    title = escape(str(chosen["title"])) if chosen else "상세 화면 명세가 필요합니다"
    summary = escape(str(chosen["purpose"])) if chosen else (
        "두 번째 화면의 이름·목적·구성요소를 설계 버전에 추가하면 상세 화면이 나타납니다."
    )
    components = [escape(str(item)) for item in chosen["components"]] if chosen else []
    cards = "".join(
        f'<article class="feature"><span class="number">{index:02d}</span>'
        f'<h2>{item}</h2><p>이 구성요소의 실제 동작과 데이터 연결은 후속 구현 단계에서 검증합니다.</p></article>'
        for index, item in enumerate(components[:8], 1)
    )
    if not cards:
        cards = '<p class="empty">이 화면의 구성요소가 아직 정의되지 않았습니다.</p>'
    if kind == "home":
        body = (
            f'<section class="hero"><span class="eyebrow">HOME · SCREEN PREVIEW</span>'
            f'<h1>{title}</h1><p>{summary}</p><span class="action">시작하기 · 시안</span></section>'
            f'<section class="features" aria-label="홈 화면 구성요소">{cards}</section>'
        )
    else:
        body = (
            f'<nav class="crumb" aria-label="현재 위치">{brand} / 상세 시안</nav>'
            f'<section class="detail"><div class="visual" aria-label="콘텐츠 이미지 자리">'
            '<span>콘텐츠 이미지 자리</span></div><div class="copy">'
            f'<span class="eyebrow">DETAIL · SCREEN PREVIEW</span><h1>{title}</h1>'
            f'<p>{summary}</p><span class="action">다음 단계 · 시안</span></div></section>'
            f'<section class="features" aria-label="상세 화면 구성요소">{cards}</section>'
        )
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{brand} · {title}</title>
<style>
:root{{font:16px/1.55 system-ui,-apple-system,"Noto Sans KR",sans-serif;color:#18263d;background:#f5f7fc}}
*{{box-sizing:border-box}}body{{margin:0}}.wrap{{max-width:1120px;margin:auto;padding:24px}}
header{{background:#101e38;color:#fff}}header .wrap{{display:flex;justify-content:space-between;align-items:center;gap:18px}}
.brand{{font-weight:800;font-size:20px}}.menu{{display:flex;gap:20px;color:#c4d1e8;font-size:14px}}
main{{min-height:650px}}.eyebrow{{font-size:12px;letter-spacing:.15em;color:#3563df;font-weight:800}}
.hero{{padding:clamp(36px,7vw,90px);margin:28px 0;background:linear-gradient(135deg,#fff,#e7efff);border-radius:28px}}
h1{{font-size:clamp(30px,5vw,62px);line-height:1.12;margin:13px 0 20px;overflow-wrap:anywhere}}
p{{color:#53627a;max-width:680px;white-space:pre-wrap;overflow-wrap:anywhere}}
.action{{display:inline-block;background:#315efb;color:#fff;border-radius:12px;padding:13px 20px;font-weight:700;margin-top:18px}}
.features{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:25px 0 50px}}
.feature{{min-height:175px;background:white;border:1px solid #dce4ef;border-radius:18px;padding:22px;overflow-wrap:anywhere}}
.feature h2{{font-size:20px;margin:10px 0}}.feature p{{font-size:13px;margin:0}}.number{{color:#3563df;font-weight:800}}
.crumb{{font-size:14px;color:#64748b;margin:12px 0 18px}}.detail{{display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:center}}
.visual{{aspect-ratio:4/3;border-radius:24px;background:linear-gradient(145deg,#dbe8ff,#a9c1ed);display:grid;place-items:center;color:#365784}}
.copy{{padding:20px 0}}.empty{{grid-column:1/-1}}
footer{{border-top:1px solid #dce4ef;color:#64748b;font-size:13px}}
@media(max-width:700px){{.wrap{{padding:16px}}.menu{{gap:10px;font-size:12px}}.features{{grid-template-columns:1fr}}.detail{{grid-template-columns:1fr}}.hero{{margin:16px 0}}}}
</style></head><body><header><div class="wrap"><span class="brand">{brand}</span>
<nav class="menu" aria-label="시안 메뉴"><span>홈</span><span>소개</span><span>상세</span></nav></div></header>
<main class="wrap">{body}</main><footer><div class="wrap">{purpose} · 화면 시안 / 기능 연결 전</div></footer>
</body></html>"""
