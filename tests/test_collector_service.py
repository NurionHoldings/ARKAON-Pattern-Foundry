import json
import socket

import pytest

from apf.collector_service import JsonCandidateProvider, SafeHttpsFetcher, _SafeRedirectHandler


def test_json_provider_loads_explicit_sources(tmp_path):
    config = tmp_path / "collector.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "python-docs",
                        "kind": "OFFICIAL_STANDARD",
                        "locator": "https://docs.python.org/3/",
                        "intent_relevance": 0.9,
                        "license_clarity": 0.9,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    loaded = list(JsonCandidateProvider(config).candidates())
    assert loaded[0].source_id == "python-docs"
    assert loaded[0].locator == "https://docs.python.org/3/"


@pytest.mark.parametrize(
    "locator",
    ["http://example.org", "https://user:password@example.org", "file:///etc/passwd"],
)
def test_fetcher_rejects_insecure_or_credential_bearing_locator(locator):
    candidate = type("Candidate", (), {"locator": locator})()
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        SafeHttpsFetcher().fetch(candidate, 10)


def test_fetcher_blocks_private_network_targets(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    candidate = type("Candidate", (), {"locator": "https://internal.example"})()
    with pytest.raises(ValueError, match="non-global"):
        SafeHttpsFetcher().fetch(candidate, 10)


def test_every_redirect_target_is_revalidated():
    checked = []
    handler = _SafeRedirectHandler(checked.append)
    request = __import__("urllib.request").request.Request("https://example.org")
    redirected = handler.redirect_request(
        request, None, 302, "Found", {}, "https://redirect.example.org/resource"
    )
    assert checked == ["https://redirect.example.org/resource"]
    assert redirected.full_url == "https://redirect.example.org/resource"
