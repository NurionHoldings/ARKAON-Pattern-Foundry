"""Named, dependency-free platform entrance effects."""
from html import escape
from pathlib import Path

EFFECT_ID = "arkaon-cinematic-gate"
EFFECT_NAME = "아르카온 시네마틱 게이트"
ALIASES = {EFFECT_ID, EFFECT_NAME, "시네마틱 게이트"}
PATTERN_TOKEN = "entry-effect:" + EFFECT_ID


def render_entry_effect(name: str = EFFECT_ID, *, title: str = "ARKAON",
                        subtitle: str = "당신의 아이디어가 현실이 되는 순간",
                        title_parts: tuple[str, str, str] | list[str] | None = None) -> str:
    if name not in ALIASES:
        raise ValueError(f"Unknown entry effect: {name}")
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
        spans = "".join(
            f'<span class="apf-word apf-word-{role}" aria-hidden="true">{escape(part)}</span>'
            for role, part in zip(("left", "center", "right"), title_parts)
        )
        title_markup = f'<span class="apf-layered" aria-label="{label}">{spans}</span>'
    else:
        title_markup = escape(title)
    template = Path(__file__).with_name("cinematic_gate.html").read_text(encoding="utf-8")
    # Split before replacement so user text resembling a slot is never reinterpreted.
    before, rest = template.split("__APF_TITLE__", 1)
    middle, after = rest.split("__APF_SUBTITLE__", 1)
    return before + title_markup + middle + escape(subtitle) + after
