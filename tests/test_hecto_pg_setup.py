import json

import pytest

from apf.hecto_pg import PGRejected
from apf.hecto_pg_setup import PUBLIC_CARD, check, configure, read_env, seed


def test_seed_four_namespaces_without_enabling_or_exposing_keys(tmp_path):
    directory = tmp_path / 'private'
    report = seed(directory)
    env = read_env(directory / 'sandbox.env')
    assert len(env) == 12
    assert len(report['platforms']) == 4
    assert all(value not in json.dumps(report) for value in PUBLIC_CARD)
    result = check(directory)
    assert all(p['keys_configured'] and not p['enabled'] for p in result['platforms'])
    assert result['status'] == 'CALLBACKS_AND_HOST_PENDING'


def test_seed_never_overwrites_credentials(tmp_path):
    seed(tmp_path)
    before = (tmp_path / 'sandbox.env').read_bytes()
    with pytest.raises(PGRejected):
        seed(tmp_path)
    assert before == (tmp_path / 'sandbox.env').read_bytes()


def test_configure_one_platform_only_and_validate_real_loader(tmp_path):
    seed(tmp_path)
    result = configure(tmp_path, 'arkaon', 'https://api.example.com',
                       'https://app.example.com/return', 'https://app.example.com/cancel')
    assert result['status'] == 'READY_FOR_SANDBOX_HOST_TEST'
    assert [p['platform'] for p in result['platforms'] if p['enabled']] == ['arkaon']
    assert result['host_env_registered'] is False
    config = json.loads((tmp_path / 'platforms.local.json').read_text())
    assert config['platforms']['arkaon']['noti_url'].endswith('/arkaon/noti')


def test_invalid_origin_does_not_activate_platform(tmp_path):
    seed(tmp_path)
    before = (tmp_path / 'platforms.local.json').read_bytes()
    with pytest.raises(PGRejected):
        configure(tmp_path, 'arkaon', 'http://untrusted.test',
                  'https://app.example.com/return', 'https://app.example.com/cancel')
    assert before == (tmp_path / 'platforms.local.json').read_bytes()
