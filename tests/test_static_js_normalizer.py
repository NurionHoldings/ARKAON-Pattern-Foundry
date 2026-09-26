
import pytest

from apf.static_js_normalizer import (
    StaticJsRejected,
    decode_obfuscated_escapes,
    normalize_minified_js,
    verify_no_verbatim_copy,
)

MINIFIED = (
    "import x from './a';export function route(){fetch('/api/start');"
    "return '\\uB098\\uB791';}eval('bad')"
)


def test_decode_obfuscated_unicode_escapes():
    assert "나랑" in decode_obfuscated_escapes("'\\uB098\\uB791'")


def test_normalize_minified_js_extracts_structure_without_storing_verbatim():
    result = normalize_minified_js(source_path="frontend/app.js", content=MINIFIED)
    assert result.import_targets == ("./a",)
    assert "/api/start" in result.route_refs
    assert result.dynamic_execution_detected is True
    assert len(result.structure_digest) == 64
    assert result.deobfuscated_preview_lines


def test_verbatim_copy_is_rejected():
    original = "function competitorBrandSpecificFeature(){return 1;}"
    with pytest.raises(StaticJsRejected, match="verbatim|similar"):
        verify_no_verbatim_copy(original=original, abstract=original)


def test_oversized_js_is_rejected():
    with pytest.raises(StaticJsRejected, match="size limit"):
        normalize_minified_js(source_path="big.js", content="x" * 600_000, max_bytes=1000)
