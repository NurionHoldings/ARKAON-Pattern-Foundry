"""Named, dependency-free platform entrance effects."""
import re
from html import escape
from math import isfinite
from pathlib import Path

from .entry_effect_presets import PRESET_CSS, list_entry_effects, resolve_effect
from .text_effects import TEXT_CSS, font_stack, render_text_segments

EFFECT_ID = "arkaon-cinematic-gate"
EFFECT_NAME = "아르카온 시네마틱 게이트"
ALIASES = {EFFECT_ID, EFFECT_NAME, "시네마틱 게이트"}
PATTERN_TOKEN = "entry-effect:" + EFFECT_ID


def render_entry_effect(name: str = EFFECT_ID, *, title: str = "ARKAON",
                        subtitle: str = "당신의 아이디어가 현실이 되는 순간",
                        title_parts: tuple[str, str, str] | list[str] | None = None,
                        accent: str = "#ad79ff", background: str = "#071522",
                        duration: float = 4.0, font: str = "system",
                        font_family: str | None = None, text_segments: list[dict] | None = None) -> str:
    effect_id = resolve_effect(name)
    stack = font_stack(font, font_family)
    if text_segments is not None and title_parts is not None and (
        not isinstance(title_parts, (list, tuple))
        or not isinstance(text_segments, list) or len(text_segments) != 3
        or any(not isinstance(item, dict) for item in text_segments)
        or [item.get("text") for item in text_segments] != list(title_parts)
    ):
        raise ValueError("Layered text_segments must match the three title_parts")
    for color in (accent, background):
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Colors must be six-digit hex values")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not isfinite(duration) or not 0.5 <= duration <= 8:
        raise ValueError("duration must be between 0.5 and 8 seconds")
    if title_parts is not None and effect_id != EFFECT_ID:
        raise ValueError("title_parts is supported only by cinematic gate")
    for value in (title, subtitle):
        if not isinstance(value, str) or not value.strip() or len(value) > 160:
            raise ValueError("Effect text must contain 1–160 characters")
    if title_parts is not None:
        if not isinstance(title_parts, (tuple, list)) or len(title_parts) != 3:
            raise ValueError("title_parts must be [left, center, right]")
        for part in title_parts:
            if not isinstance(part, str) or not part.strip() or len(part) > 24:
                raise ValueError("Each title part must contain 1–24 characters")
        label = escape(" ".join(title_parts), quote=True)
        pieces = []
        for index, (role, part) in enumerate(zip(("left", "center", "right"), title_parts)):
            content = render_text_segments([text_segments[index]], font=font, font_family=font_family) if text_segments is not None else escape(part)
            pieces.append(f'<span class="apf-word apf-word-{role}" aria-hidden="true">{content}</span>')
        spans = "".join(pieces)
        title_markup = f'<span class="apf-layered" aria-label="{label}">{spans}</span>'
    elif text_segments is not None:
        title_markup = render_text_segments(text_segments, font=font, font_family=font_family)
    elif effect_id == "arkaon-stagger-rise":
        spans = "".join(
            f'<span class="apf-char" aria-hidden="true" style="--apf-progress:{i/max(1,len(title)-1):.6f}">{escape(char)}</span>'
            for i, char in enumerate(title)
        )
        title_markup = f'<span aria-label="{escape(title, quote=True)}">{spans}</span>'
    else:
        title_markup = escape(title)
    template = Path(__file__).with_name("cinematic_gate.html").read_text(encoding="utf-8")
    template = template.replace('data-effect="arkaon-cinematic-gate"', f'data-effect="{effect_id}"')
    if text_segments is not None and title_parts is None:
        template = template.replace('class="apf-title"', 'class="apf-title apf-custom-title"')
    style = f":root{{--apf-accent:{accent};--apf-background:{background};--apf-duration:{duration}s}}"
    template = template.replace("</style>", style + PRESET_CSS + TEXT_CSS + f".apf-title,.apf-subtitle{{font-family:{stack}}}" + "</style>", 1)
    # Split before replacement so user text resembling a slot is never reinterpreted.
    before, rest = template.split("__APF_TITLE__", 1)
    middle, after = rest.split("__APF_SUBTITLE__", 1)
    return before + title_markup + middle + escape(subtitle) + after


def main() -> None:
    """Export a named effect without requiring the platform server."""
    import argparse
    import json
    parser = argparse.ArgumentParser(description="ARKAON entrance effect export")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--effect", default=EFFECT_ID)
    parser.add_argument("--title", default="ARKAON")
    parser.add_argument("--subtitle", default="당신의 아이디어가 현실이 되는 순간")
    parser.add_argument("--parts", nargs=3, metavar=("LEFT", "CENTER", "RIGHT"))
    parser.add_argument("--accent", default="#ad79ff")
    parser.add_argument("--background", default="#071522")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--font", default="system")
    parser.add_argument("--font-family")
    parser.add_argument("--text-segments", type=Path, help="JSON file containing segment options")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.list:
        print(json.dumps(list_entry_effects(), ensure_ascii=False, indent=2))
        return
    if args.output is None:
        parser.error("--output is required unless --list is used")
    try:
        page = render_entry_effect(args.effect, title=args.title, subtitle=args.subtitle,
                                   title_parts=args.parts, accent=args.accent,
                                   background=args.background, duration=args.duration,
                                   font=args.font, font_family=args.font_family,
                                   text_segments=json.loads(args.text_segments.read_text(encoding="utf-8")) if args.text_segments else None)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
