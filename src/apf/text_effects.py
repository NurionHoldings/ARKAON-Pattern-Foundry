"""Independent text motion and selectable local font stacks."""
import re
from html import escape
from math import isfinite

FONTS = {
    'system': ('시스템 기본', 'system-ui, sans-serif'),
    'gothic': ('맑은 고딕', '"Malgun Gothic", "Apple SD Gothic Neo", sans-serif'),
    'serif': ('바탕·명조', 'Batang, "AppleMyungjo", serif'),
    'gulim': ('굴림', 'Gulim, sans-serif'),
    'arial': ('Arial', 'Arial, sans-serif'),
    'georgia': ('Georgia', 'Georgia, serif'),
    'mono': ('고정폭', 'Consolas, "Courier New", monospace'),
}
ENTRANCES = ('none', 'fade-in', 'rise', 'zoom-in', 'flip-in')
EXITS = ('none', 'fade-out', 'sink', 'zoom-out')
GLOWS = ('none', 'glow', 'pulse', 'shine')
TEXT_CSS = r'''
.apf-custom-title{animation:none!important;background:none!important;color:#eee3d4!important;filter:none!important;font-size:clamp(1.5rem,6vw,6rem)}
.apf-text-group{display:inline-flex;flex-wrap:wrap;gap:.25em;justify-content:center;align-items:baseline;max-width:100%}
.apf-text-segment{display:inline-block;overflow-wrap:anywhere;max-width:100%;font-family:var(--apf-font);font-weight:var(--apf-weight,800);color:var(--apf-color,#eee3d4);animation:var(--apf-enter-name,apf-text-still) var(--apf-in-duration) ease var(--apf-delay) both}
.apf-text-exit{display:inline-block;max-width:100%;animation:var(--apf-exit-name,apf-text-still) var(--apf-out-duration) ease var(--apf-exit-delay) forwards}
.apf-text-glow{display:inline-block;max-width:100%}
.apf-text-glow[data-glow="glow"]{text-shadow:0 0 8px var(--apf-glow-color),0 0 22px var(--apf-glow-color)}
.apf-text-glow[data-glow="pulse"]{animation:apf-text-pulse 2s ease-in-out var(--apf-delay) 3 alternate both}
.apf-text-glow[data-glow="shine"]{background:linear-gradient(110deg,var(--apf-color) 35%,#fff 48%,var(--apf-glow-color) 52%,var(--apf-color) 65%);background-size:250% 100%;background-clip:text;color:transparent;animation:apf-text-shine 2s ease var(--apf-delay) 3 both}
@keyframes apf-text-still{from{transform:none}to{transform:none}}
@keyframes apf-text-fade-in{from{opacity:0}to{opacity:1}}
@keyframes apf-text-rise{from{opacity:0;transform:translateY(.7em)}to{opacity:1;transform:none}}
@keyframes apf-text-zoom-in{from{opacity:0;transform:scale(.3)}to{opacity:1;transform:scale(1)}}
@keyframes apf-text-flip-in{from{opacity:0;transform:perspective(600px) rotateY(-90deg)}to{opacity:1;transform:none}}
@keyframes apf-text-fade-out{to{opacity:0}}
@keyframes apf-text-sink{to{opacity:0;transform:translateY(.7em)}}
@keyframes apf-text-zoom-out{to{opacity:0;transform:scale(.3)}}
@keyframes apf-text-pulse{from{text-shadow:0 0 4px var(--apf-glow-color)}to{text-shadow:0 0 14px var(--apf-glow-color),0 0 28px var(--apf-glow-color)}}
@keyframes apf-text-shine{from{background-position:100% 0}to{background-position:0 0}}
@media(prefers-reduced-motion:reduce){.apf-text-segment,.apf-text-exit,.apf-text-glow{animation:none!important;opacity:1!important;transform:none!important}.apf-text-glow[data-glow="shine"]{background:none;color:var(--apf-color)}}
'''


def font_stack(font: str = 'system', font_family: str | None = None) -> str:
    if font not in FONTS:
        raise ValueError('Unknown font choice')
    if font_family is not None:
        if not isinstance(font_family, str) or not re.fullmatch(r'[\w -]{1,80}', font_family):
            raise ValueError('Invalid custom font family')
        return f'"{font_family}", {FONTS[font][1]}'
    return FONTS[font][1]


def _seconds(value: object, maximum: float = 30) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= maximum:
        raise ValueError('Text timing must be finite and between 0 and 30 seconds')
    return float(value)


def render_text_segments(segments: list[dict], *, font: str, font_family: str | None) -> str:
    if not isinstance(segments, list) or not 1 <= len(segments) <= 12:
        raise ValueError('text_segments requires 1–12 objects')
    output, labels = [], []
    for item in segments:
        if not isinstance(item, dict):
            raise ValueError('Each text segment must be an object')  # noqa: TRY004 — renderer uses ValueError
        text = item.get('text', '')
        if not isinstance(text, str) or not text.strip() or len(text) > 80:
            raise ValueError('Segment text requires 1–80 characters')
        enter, leave, glow = item.get('enter', 'fade-in'), item.get('exit', 'none'), item.get('glow', 'none')
        if enter not in ENTRANCES or leave not in EXITS or glow not in GLOWS:
            raise ValueError('Unknown individual text effect')
        delay = _seconds(item.get('delay', 0))
        incoming = _seconds(item.get('duration', 1))
        hold = _seconds(item.get('hold', 2))
        outgoing = _seconds(item.get('exit_duration', 1))
        stack = font_stack(item.get('font', font), item.get('font_family', font_family))
        color, light = item.get('color', '#eee3d4'), item.get('glow_color', '#ad79ff')
        if any(not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in (color, light)):
            raise ValueError('Text colors must be six-digit hex')
        weight = item.get('weight', 800)
        if isinstance(weight, bool) or not isinstance(weight, int) or weight not in range(100, 1000, 100):
            raise ValueError('Font weight requires 100–900 in steps of 100')
        enter_name = 'apf-text-still' if enter == 'none' else 'apf-text-' + enter
        exit_name = 'apf-text-still' if leave == 'none' else 'apf-text-' + leave
        style = (f'--apf-font:{stack};--apf-weight:{weight};--apf-color:{color};--apf-glow-color:{light};'
                 f'--apf-enter-name:{enter_name};--apf-exit-name:{exit_name};--apf-delay:{delay}s;'
                 f'--apf-in-duration:{incoming}s;--apf-out-duration:{outgoing}s;--apf-exit-delay:{delay+incoming+hold}s')
        output.append(f'<span class="apf-text-segment" style="{escape(style, quote=True)}" aria-hidden="true">'
                      f'<span class="apf-text-exit"><span class="apf-text-glow" data-glow="{glow}">{escape(text)}</span></span></span>')
        labels.append(text)
    return f'<span class="apf-text-group" aria-label="{escape(" ".join(labels), quote=True)}">'+''.join(output)+'</span>'
