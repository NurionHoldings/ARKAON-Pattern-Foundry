import pytest
from apf.entry_effects import render_entry_effect, EFFECT_NAME, PATTERN_TOKEN
from apf.co_creation_codegen import _render_section_stub


def test_named_effect_and_codegen():
    assert "AGAIN MY LIFE" in render_entry_effect(EFFECT_NAME, title="AGAIN MY LIFE")
    assert _render_section_stub(section_id="intro", purpose="진입", pattern_token=PATTERN_TOKEN, style_tags=()) == render_entry_effect()


def test_escape_text_and_validate_name():
    page = render_entry_effect(title="<script>bad</script>__APF_SUBTITLE__", subtitle="A & B")
    assert "<script>bad</script>" not in page
    assert "&lt;script&gt;" in page
    assert "__APF_SUBTITLE__" in page
    assert "A &amp; B" in page
    with pytest.raises(ValueError):
        render_entry_effect("unknown")
    with pytest.raises(ValueError):
        render_entry_effect(title="")


def test_layered_words_have_independent_order_and_safe_text():
    page = render_entry_effect(title_parts=['더', '아리랑', '스토어'])
    assert 'apf-word-left" aria-hidden="true">더' in page
    assert 'apf-word-right" aria-hidden="true">스토어' in page
    assert 'apf-word-center" aria-hidden="true">아리랑' in page
    assert 'animation-delay:.4s' in page
    assert 'animation-delay:1.6s' in page
    assert 'animation-delay:2.8s' in page
    assert 'aria-label="더 아리랑 스토어"' in page
    assert '&lt;script&gt;' in render_entry_effect(title_parts=['더', '<script>', '스토어'])
    with pytest.raises(ValueError):
        render_entry_effect(title_parts=['더', '아리랑'])
