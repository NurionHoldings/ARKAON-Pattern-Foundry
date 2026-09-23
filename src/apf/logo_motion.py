"""Scriptless motion export for owner-bound, generated logo SVGs."""

from __future__ import annotations

from typing import Literal
from xml.etree import ElementTree

Motion = Literal["float", "pulse", "spin"]
_NS = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", _NS)

_KEYFRAMES = {
    "float": "0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}",
    "pulse": "0%,100%{transform:scale(1)}50%{transform:scale(1.08)}",
    "spin": "0%,100%{transform:rotate(0deg)}50%{transform:rotate(18deg)}",
}


def animate_generated_logo(svg: str, motion: Motion) -> str:
    """Add reversible visual motion to a server-generated SVG, without script or external assets.

    The caller must retrieve and authorize the generated logo from LogoDraftStore.
    This function is deliberately not an arbitrary SVG upload processor.
    """
    if motion not in _KEYFRAMES:
        raise ValueError("LOGO_MOTION_INVALID")
    root = ElementTree.fromstring(svg)
    if root.tag != f"{{{_NS}}}svg":
        raise ValueError("LOGO_MOTION_INVALID_SVG")
    mark = root.find(f"{{{_NS}}}g")
    if mark is None:
        raise ValueError("LOGO_MOTION_INVALID_SVG")
    mark.set("class", "apf-motion-mark")
    mark.set("style", "transform-box:view-box;transform-origin:86px 86px")
    style = ElementTree.Element(f"{{{_NS}}}style")
    style.text = (
        f"@keyframes apf-logo-motion{{{_KEYFRAMES[motion]}}}"
        ".apf-motion-mark{animation:apf-logo-motion 2.4s ease-in-out infinite}"
        "@media (prefers-reduced-motion:reduce){.apf-motion-mark{animation:none}}"
    )
    root.insert(0, style)
    return ElementTree.tostring(root, encoding="unicode")
