from pathlib import Path

UI = Path("src/apf/logo_draft_ui.html").read_text(encoding="utf-8")


def test_logo_ui_exposes_complete_owner_journey_and_accessible_states():
    """Keep the static client contract aligned with the owner-bound logo endpoints."""
    for value in (
        "/v1/console/logo-drafts",
        "/revisions",
        "/rollback/",
        "/download.svg",
        'aria-live="polite"',
        "aria-pressed",
        "reportValidity()",
        "저장된 SVG 다운로드",
        "버전 기록",
        "움직임 미리보기",
        "motionImage.src=url",
        "참고 이미지 미리보기",
        "도형·텍스트 기반 SVG 시안입니다",
    ):
        assert value in UI


def test_logo_ui_keeps_navigation_between_creation_and_review_surfaces():
    assert 'href="/site-drafts"' in UI
    assert 'href="/console"' in UI
    assert 'href="/logo-drafts"' in Path("src/apf/console_ui.html").read_text(encoding="utf-8")
    assert 'href="/logo-drafts"' in Path("src/apf/conversational_site_draft_ui.html").read_text(
        encoding="utf-8"
    )
