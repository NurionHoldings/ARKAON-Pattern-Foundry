from datetime import UTC, datetime

from apf.reference_url_style import observe_reference_style

NOW = datetime(2031, 9, 1, tzinfo=UTC)


def test_observe_reference_style_from_html_payload():
    html = b"<html><h1>Step 1</h1><p>CTA</p><section>FAQ</section></html>"
    profile = observe_reference_style(
        url="https://example.test/",
        now=NOW,
        fetch_payload=lambda _url: html,
    )
    assert profile.source_url == "https://example.test/"
    assert profile.style_tags
    assert profile.observation_digest
