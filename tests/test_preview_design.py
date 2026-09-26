from apf.conversational_site_draft import _static_page
from apf.platform_page_preview import render_page_mockup


def test_preview_pages_share_tokens_and_distinct_layouts():
    brief = {"name": "부업장터", "purpose": "벌거리를 찾고 연결합니다."}
    screens = [
        {"screen_id": "home", "title": "벌거리 탐색", "purpose": "일감을 찾습니다.",
         "components": ["검색", "추천"]},
        {"screen_id": "detail", "title": "벌거리 상세", "purpose": "조건을 확인합니다.",
         "components": ["조건", "지원"]},
    ]
    landing = _static_page("부업장터", "소개 문구", 1)
    home = render_page_mockup(brief, screens, "home")
    detail = render_page_mockup(brief, screens, "detail")
    for page in (landing, home, detail):
        assert "--night: #0b172a" in page
        assert "prefers-reduced-motion: reduce" in page
        assert "max-width: 760px" in page
        assert "<script" not in page
        assert "https://" not in page
    assert "landing-hero" in landing
    assert '<section class="preview-hero"' in home and '<section class="detail-stage"' not in home
    assert '<section class="detail-stage"' in detail and '<section class="preview-hero"' not in detail


def test_preview_escapes_user_text_and_marks_decorative_content():
    page = _static_page("<img src=x>", "내용 <script>alert(1)</script>", 1)
    assert "&lt;img src=x&gt;" in page
    assert "&lt;script&gt;" in page
    assert "<script" not in page
    assert 'aria-hidden="true"' in page
