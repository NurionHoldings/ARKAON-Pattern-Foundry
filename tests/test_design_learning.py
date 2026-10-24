from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.design_learning import build_report, observe, run, validate_url

NOW = datetime(2026, 10, 24, tzinfo=UTC)
SOURCE = 'https://www.miricanvas.com/en/features/logo-maker'
SHA = 'a' * 40
CONTENT = b'<html>resize spacing alignment logo color font</html>'


def test_public_claims_produce_concrete_tasks_but_never_improvement_acceptance():
    report = build_report([observe(SOURCE, CONTENT, NOW)], SHA)
    assert len(report['tasks']) == 2
    for task in report['tasks']:
        assert task['acceptance'] and task['paths'] and task['comparison_plan']
        assert task['baseline_status'] == 'MEASUREMENT_REQUIRED'
        assert task['improvement_accepted'] is False
        assert task['automatic_implement_allowed'] is False


def test_scripts_are_not_learning_instructions_or_feature_evidence():
    observation = observe(SOURCE, b'<script>resize spacing alignment</script>hello', NOW)
    assert observation['features'] == []
    assert observation['executed_product_test'] is False


@pytest.mark.parametrize('url', ['http://www.miricanvas.com/', 'https://evil.example/',
                                 'https://www.miricanvas.com.evil.example/',
                                 'https://user@www.miricanvas.com/',
                                 'https://www.miricanvas.com:8443/'])
def test_network_boundary(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_changed_fetch_time_does_not_duplicate_or_overwrite_review_packet(tmp_path):
    for day in (24, 25):
        run(tmp_path, [SOURCE], SHA, datetime(2026, 10, day, tzinfo=UTC),
            fetch=lambda _: CONTENT, dry_run=False)
    packets = list((tmp_path / 'inbox/eternian-review').glob('*.json'))
    assert len(packets) == 2
    original = packets[0].read_bytes()
    run(tmp_path, [SOURCE], SHA, NOW, fetch=lambda _: CONTENT, dry_run=False)
    assert packets[0].read_bytes() == original


def test_source_failure_isolated_and_dry_run_has_no_writes(tmp_path):
    urls = [SOURCE, 'https://help.miricanvas.com/hc/ko/articles/4411396671769']

    def fetch(url):
        if url == SOURCE:
            raise OSError('offline')
        return CONTENT

    report = run(tmp_path, urls, SHA, NOW, fetch=fetch)
    assert len(report['failures']) == 1
    assert len(report['tasks']) == 2
    assert list(tmp_path.iterdir()) == []


def test_baseline_must_be_bound_to_full_commit():
    with pytest.raises(ValueError, match='FULL_BASELINE'):
        build_report([], 'main')


def test_created_packet_is_consumable_by_existing_mailbox(tmp_path: Path):
    from apf.arkaon_mailbox import ArkaonMailbox

    run(tmp_path, [SOURCE], SHA, NOW, fetch=lambda _: CONTENT, dry_run=False)
    items = ArkaonMailbox(foundry_root=tmp_path).sync_from_inbox(now=NOW)
    assert len(items) == 2
