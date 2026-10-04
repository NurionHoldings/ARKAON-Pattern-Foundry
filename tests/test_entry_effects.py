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


from apf.entry_effect_presets import PRESETS, resolve_effect, list_entry_effects


@pytest.mark.parametrize('effect_id', PRESETS)
def test_registry_supports_all_names_and_safe_customization(effect_id):
    label = PRESETS[effect_id][0]
    assert resolve_effect(label) == effect_id
    page = render_entry_effect(label, title='<script>probe</script>',
                               accent='#abcdef', background='#123456', duration=2)
    assert f'data-effect="{effect_id}"' in page
    assert '<script>probe</script>' not in page
    assert '--apf-accent:#abcdef' in page
    assert '--apf-duration:2s' in page
    assert 'effect:gate.dataset.effect' in page
    assert len(list_entry_effects()) == 9


@pytest.mark.parametrize('options', [
    {'accent': '#fff;}</style><script>bad</script>'},
    {'background': 'red'}, {'duration': float('nan')}, {'duration': True},
    {'duration': 20}, {'duration': .1},
    {'name': 'arkaon-iris-reveal', 'title_parts': ['더','아리랑','스토어']},
])
def test_options_reject_css_injection_and_invalid_motion(options):
    with pytest.raises(ValueError):
        render_entry_effect(**options)
