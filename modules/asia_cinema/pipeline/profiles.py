"""Render/encode profiles from the STEP5 design spec (asia-cinema-design-20261025-01)."""
from __future__ import annotations

from dataclasses import dataclass

FPS = 24
DURATION_SEC = 16
FRAME_COUNT = FPS * DURATION_SEC
NURION_REFERENCE_MP4_SHA256 = "550fffe4bf0f30d157ceabe776c10238d16f8465b37e201acf4d047909395c62"


@dataclass(frozen=True)
class Profile:
    name: str
    width: int
    height: int
    crf: int


PROFILES = {
    "preview": Profile("preview", 960, 540, 23),
    "final": Profile("final", 1920, 1080, 18),
}
