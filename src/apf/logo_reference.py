"""Ephemeral raster reference analysis for logo drafting; no original bytes are persisted."""

from __future__ import annotations

import base64
import binascii
import io
from hashlib import sha256

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

MAX_BYTES = 2_000_000
MAX_PIXELS = 4_000_000


class ImageReferenceError(ValueError):
    pass


class ImageReferenceRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=2_700_000)
    compare_base64: str | None = Field(default=None, max_length=2_700_000)


def _image(encoded: str) -> tuple[Image.Image, bytes, str]:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ImageReferenceError("IMAGE_REFERENCE_INVALID_BASE64") from exc
    if not raw or len(raw) > MAX_BYTES:
        raise ImageReferenceError("IMAGE_REFERENCE_SIZE")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "PNG"
    elif raw.startswith(b"\xff\xd8\xff"):
        kind = "JPEG"
    else:
        raise ImageReferenceError("IMAGE_REFERENCE_FORMAT")
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.format != kind or opened.width * opened.height > MAX_PIXELS:
                raise ImageReferenceError("IMAGE_REFERENCE_DIMENSIONS")
            opened.load()
            image = ImageOps.exif_transpose(opened).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageReferenceError("IMAGE_REFERENCE_INVALID") from exc
    background = Image.new("RGBA", image.size, "white")
    background.alpha_composite(image)
    return background.convert("RGB"), raw, kind


def _features(image: Image.Image, raw: bytes, kind: str) -> dict[str, object]:
    small = image.resize((9, 8), Image.Resampling.LANCZOS).convert("L")
    pixels = list(small.getdata())
    bits = sum(
        1 << (row * 8 + col)
        for row in range(8)
        for col in range(8)
        if pixels[row * 9 + col] > pixels[row * 9 + col + 1]
    )
    sample = image.resize((64, 64), Image.Resampling.LANCZOS)
    colors = sample.quantize(colors=5).convert("RGB").getcolors(4096) or []
    colors.sort(reverse=True, key=lambda pair: pair[0])
    palette = [f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}" for _, rgb in colors[:5]]
    return {
        "digest": "sha256:" + sha256(raw).hexdigest(),
        "format": kind.lower(),
        "width": image.width,
        "height": image.height,
        "aspect_ratio": round(image.width / image.height, 3),
        "palette": palette,
        "visual_hash": f"{bits:016x}",
    }


def analyze_reference(request: ImageReferenceRequest) -> dict[str, object]:
    first, raw, kind = _image(request.image_base64)
    result: dict[str, object] = {"reference": _features(first, raw, kind)}
    if request.compare_base64 is not None:
        second, other_raw, other_kind = _image(request.compare_base64)
        comparison = _features(second, other_raw, other_kind)
        distance = (
            int(str(result["reference"]["visual_hash"]), 16)
            ^ int(str(comparison["visual_hash"]), 16)
        ).bit_count()
        result["comparison"] = comparison
        result["visual_hash_distance"] = distance
        result["note"] = "0~64의 해시 거리. 낮을수록 축소한 명암 구조가 비슷하며 권리 판단에는 사용할 수 없습니다."
    return result
