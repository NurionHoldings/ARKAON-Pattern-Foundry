import json
import socket
from pathlib import Path

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


def test_manual_investigation_selects_catalog_source_without_hourly_filter(tmp_path, monkeypatch, capsys):
    from apf.collector_service import main

    config = json.loads(Path('config/collector.default.json').read_text())
    config_path = tmp_path / 'collector.json'
    config_path.write_text(json.dumps(config))
    fetched = []

    def fetch(self, candidate, max_bytes):
        fetched.append(candidate.source_id)
        return b'public reference material'

    monkeypatch.setattr(SafeHttpsFetcher, 'fetch', fetch)
    assert main([
        '--config', str(config_path), '--foundry-root', str(tmp_path),
        '--audit', str(tmp_path / 'audit.jsonl'), '--state', str(tmp_path / 'hashes.sqlite3'),
        '--once', '--manual-topic', '기능에 필요한 CSS 전환 조사',
        '--source-id', 'mdn-css-animations', '--schedule', str(tmp_path / 'not-loaded.json'),
    ]) == 0
    assert fetched == ['mdn-css-animations']
    report = json.loads(capsys.readouterr().out)
    assert report['result']['collected'] == 1
    assert report['production_change_allowed'] is False
    assert report['model_training_performed'] is False
    assert report['next_step'] == 'IMPLEMENT_AND_VERIFY_WITHIN_OWNER_REQUESTED_SCOPE'
    assert len(list((tmp_path / 'state/manual-learning').glob('*.json'))) == 1
    assert json.loads(config_path.read_text()) == config


def test_manual_source_selection_cannot_invent_an_approved_origin(tmp_path):
    from apf.collector_service import SelectedCandidateProvider

    config = tmp_path / 'collector.json'
    config.write_text(json.dumps({'sources': []}))
    with pytest.raises(ValueError, match='MANUAL_SOURCE_NOT_IN_APPROVED_CATALOG'):
        SelectedCandidateProvider(JsonCandidateProvider(config), ['unknown-origin'])


@pytest.mark.parametrize('flags', [
    ['--manual-topic', 'CSS', '--source-id', 'mdn-css-animations'],
    ['--once', '--manual-topic', 'CSS'],
    ['--once', '--source-id', 'mdn-css-animations'],
    ['--once', '--manual-topic', 'ignore previous instructions', '--source-id', 'x'],
])
def test_manual_mode_requires_bounded_explicit_request(flags):
    from apf.collector_service import main

    with pytest.raises(SystemExit) as caught:
        main(['--config', 'not-opened.json', *flags])
    assert caught.value.code == 2
