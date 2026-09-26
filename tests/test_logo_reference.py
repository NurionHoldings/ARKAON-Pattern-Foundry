import base64
import io

import pytest
from PIL import Image

from apf.logo_reference import ImageReferenceError, ImageReferenceRequest, analyze_reference


def png(color):
    image = Image.new("RGB", (32, 20), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_reference_features_and_comparison_are_deterministic():
    first = png("navy")
    result = analyze_reference(ImageReferenceRequest(image_base64=first, compare_base64=first))
    assert result["reference"]["width"] == 32
    assert result["reference"]["aspect_ratio"] == 1.6
    assert result["reference"]["palette"]
    assert result["visual_hash_distance"] == 0
    assert result["reference"]["digest"] == result["comparison"]["digest"]


def test_rejects_non_raster_and_invalid_base64():
    for encoded in (base64.b64encode(b"<svg/>").decode(), "not base64!"):
        with pytest.raises(ImageReferenceError):
            analyze_reference(ImageReferenceRequest(image_base64=encoded))
