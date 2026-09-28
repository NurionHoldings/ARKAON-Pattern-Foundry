import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("build_netlify_site", "tools/build_netlify_site.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
backend_origin, build = module.backend_origin, module.build


def test_netlify_home_build_without_backend_keeps_demo_link_hidden(monkeypatch):
    monkeypatch.delenv("ARKAON_API_ORIGIN", raising=False)
    build()
    site = Path("dist")
    assert json.loads((site / "api-config.json").read_text()) == {"inspection_available": False}
    assert (site / "_redirects").read_text() == ""
    html = (site / "index.html").read_text()
    assert 'id="inspection-link"' in html and 'href="/inspection" hidden' in html
    assert all(label in html for label in ("50,000", "10,000", "60,000"))
    assert (site / "assets" / "home.css").stat().st_size > 1000
    assert "[hidden]{display:none!important}" in (site / "assets" / "home.css").read_text()


def test_netlify_home_proxies_only_inspection_to_https_backend(monkeypatch):
    monkeypatch.setenv("ARKAON_API_ORIGIN", "https://api.example.test")
    build()
    assert Path("dist/_redirects").read_text() == (
        "/inspection/* https://api.example.test/inspection/:splat 200\n"
    )
    assert json.loads(Path("dist/api-config.json").read_text()) == {
        "inspection_available": True,
    }
    for bad in ("http://api.example.test", "https://name:pass@api.example.test",
                "https://api.example.test/path", "https://api.example.test/?x=1"):
        with pytest.raises(ValueError):
            backend_origin(bad)
