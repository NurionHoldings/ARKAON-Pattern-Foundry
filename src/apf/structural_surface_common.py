"""Shared structural surface helpers for SNS and emerging-market watch."""

from __future__ import annotations

import json
import re
from hashlib import sha256

_META_PROPERTY = re.compile(r'<meta[^>]+property=["\']([^"\']+)["\']', re.IGNORECASE)
_LINK_HREF = re.compile(r"<a\b[^>]*\bhref=", re.IGNORECASE)
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc=", re.IGNORECASE)
_IFRAME = re.compile(r"<iframe\b", re.IGNORECASE)
_VIDEO = re.compile(r"<video\b", re.IGNORECASE)
_HEADING = re.compile(r"<h[1-6]\b", re.IGNORECASE)


def digest_document(document: dict[str, object]) -> str:
    return sha256(json.dumps(document, sort_keys=True).encode("utf-8")).hexdigest()


def count_bin(count: int) -> str:
    if count <= 1:
        return "0-1"
    if count <= 3:
        return "2-3"
    if count <= 5:
        return "4-5"
    return "6+"


def structural_signals_from_public_html(payload: bytes, *, context: str) -> dict[str, object]:
    text = payload.decode("utf-8", errors="replace")
    lowered = text.casefold()
    for forbidden in ("password", "credential", "access_token", "sessionid"):
        if forbidden in lowered:
            raise ValueError(f"{context}: sensitive marker blocked")
    og_properties = sorted({match.group(1).casefold() for match in _META_PROPERTY.finditer(text)})
    link_count = len(_LINK_HREF.findall(text))
    script_count = len(_SCRIPT_SRC.findall(text))
    heading_count = len(_HEADING.findall(text))
    return {
        "og_property_count": len(og_properties),
        "og_property_samples": og_properties[:8],
        "link_count_bin": count_bin(link_count),
        "heading_count_bin": count_bin(heading_count),
        "script_src_count_bin": count_bin(script_count),
        "has_iframe": bool(_IFRAME.search(text)),
        "has_video_tag": bool(_VIDEO.search(text)),
        "payload_bytes_bin": count_bin(max(1, len(payload) // 100_000)),
    }
