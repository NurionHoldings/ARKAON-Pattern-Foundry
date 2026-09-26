from pathlib import Path

UI = Path("src/apf/business_card_ui.html").read_text(encoding="utf-8")


def test_business_card_ui_has_owner_journey_and_safe_vector_claims():
    for value in (
        "/v1/console/logo-drafts",
        "/v1/console/business-cards",
        "/revisions",
        "/rollback/",
        "/download/",
        'aria-live="polite"',
        "reportValidity()",
        "결정적인 벡터 SVG",
        "앞면 SVG 다운로드",
        "뒷면 SVG 다운로드",
    ):
        assert value in UI


def test_business_card_navigation_is_connected():
    assert 'href="/business-cards"' in Path("src/apf/logo_draft_ui.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/business-cards"' in Path("src/apf/console_ui.html").read_text(encoding="utf-8")
    assert 'href="/logo-drafts"' in UI and 'href="/site-drafts"' in UI
