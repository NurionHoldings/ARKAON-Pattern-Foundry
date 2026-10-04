import pytest

from apf.co_creation_codegen import _render_section_stub
from apf.entry_effects import EFFECT_NAME, PATTERN_TOKEN, render_entry_effect


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


from apf.entry_effect_presets import PRESETS, list_entry_effects, resolve_effect


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


@pytest.mark.parametrize('enter', ['none','fade-in','rise','zoom-in','flip-in'])
def test_individual_text_effects_and_fonts(enter):
    page = render_entry_effect(font='gothic', text_segments=[
        {'text':'더', 'enter':enter, 'glow':'glow', 'font':'serif'},
        {'text':'아리랑', 'delay':1, 'glow':'pulse', 'exit':'fade-out', 'hold':2},
        {'text':'스토어', 'delay':2, 'glow':'shine', 'font_family':'Pretendard'},
    ])
    assert 'aria-label="더 아리랑 스토어"' in page
    assert 'data-glow="pulse"' in page
    assert '--apf-exit-delay:4.0s' in page
    assert 'Batang' in page and 'Pretendard' in page
    assert 'apf-custom-title' in page


@pytest.mark.parametrize('options', [
    {'font':'missing'}, {'font_family':'x;}</style><script>bad</script>'},
    {'text_segments':[]}, {'text_segments':[{'text':'hi','glow':'missing'}]},
    {'text_segments':[{'text':'hi','delay':float('nan')}]},
    {'text_segments':[{'text':'hi','color':'red'}]},
    {'text_segments':[{'text':'hi','weight':850}]},
    {'title_parts':['더','아리랑','스토어'],'text_segments':[{'text':'hi'}]},
])
def test_individual_effect_validation(options):
    with pytest.raises(ValueError):
        render_entry_effect(**options)


def test_layered_words_can_combine_individual_glow_and_exit():
    page = render_entry_effect(title_parts=['더','아리랑','스토어'], text_segments=[
        {'text':'더','glow':'glow'}, {'text':'아리랑','glow':'shine','font':'serif'},
        {'text':'스토어','exit':'fade-out','delay':2},
    ])
    assert 'apf-word-left' in page and 'apf-word-center' in page
    assert 'data-glow="shine"' in page
    assert '--apf-exit-name:apf-text-fade-out' in page
