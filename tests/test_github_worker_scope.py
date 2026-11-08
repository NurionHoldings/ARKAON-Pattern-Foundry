import importlib.util
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('worker_scope', Path(__file__).parents[1] / 'scripts/guard_github_worker.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
NOW = datetime(2026, 11, 8, tzinfo=UTC)
REPO = 'NurionHoldings/ARKAON-Pattern-Foundry'


def sample():
    pr = {'body': 'ARKAON_TASK: test-task', 'user': {'login': 'copilot-swe-agent[bot]'},
          'base': {'ref': 'main'}, 'head': {'ref': 'copilot/fix', 'sha': 'a' * 40,
                                          'repo': {'full_name': REPO}}}
    task = {'schema_version': 'apf.github-coding-task/v1', 'task_id': 'test-task',
            'state': 'APPROVED_FOR_ONE_TASK', 'expires_at': (NOW + timedelta(days=1)).isoformat(),
            'base_branch': 'main', 'repository': REPO,
            'allowed_actors': ['copilot-swe-agent[bot]'], 'allowed_paths': ['services/test.js'],
            'expected_file_blobs': {'services/test.js': 'b' * 40},
            'max_changed_files': 1, 'max_changed_lines': 30}
    changes = [{'filename': 'services/test.js', 'status': 'modified', 'additions': 5, 'deletions': 1}]
    return pr, task, changes


def check(pr, task, changes, **kwargs):
    return guard.check_scope(pr, task, changes, now=NOW,
                             base_blobs=kwargs.get('blobs', task['expected_file_blobs']),
                             head_modes=kwargs.get('modes', {'services/test.js': '100644'}))


def test_valid_scoped_worker_change_is_head_bound():
    pr, task, changes = sample()
    report = check(pr, task, changes)
    assert report['scope_passed'] is True
    assert report['head_sha'] == pr['head']['sha']


def test_bot_cannot_remove_or_duplicate_the_task_marker():
    pr, task, changes = sample()
    for body in ['', 'ARKAON_TASK: test-task\nARKAON_TASK: other-task']:
        pr['body'] = body
        with pytest.raises(guard.ScopeDenied, match='EXACTLY_ONE'):
            check(pr, task, changes)


@pytest.mark.parametrize(('mutation', 'code'), [
    ('outside', 'OUT_OF_SCOPE'), ('rename', 'OUT_OF_SCOPE'), ('delete', 'DELETION'),
    ('oversized', 'BUDGET'), ('many_files', 'COUNT'), ('actor', 'ACTOR'),
    ('fork', 'REPOSITORY'), ('branch', 'BASE_BRANCH'), ('expired', 'EXPIRED'),
    ('revoked', 'NOT_APPROVED'), ('task', 'BINDING'),
])
def test_scope_or_authority_changes_are_rejected(mutation, code):
    pr, task, changes = sample()
    if mutation == 'outside':
        changes[0]['filename'] = 'services/other.js'
    elif mutation == 'rename':
        changes[0]['previous_filename'] = 'services/other.js'
    elif mutation == 'delete':
        changes[0]['status'] = 'removed'
    elif mutation == 'oversized':
        changes[0]['additions'] = 100
    elif mutation == 'many_files':
        changes.append(deepcopy(changes[0]))
    elif mutation == 'actor':
        pr['user']['login'] = 'not-the-worker'
    elif mutation == 'fork':
        pr['head']['repo']['full_name'] = 'other/repo'
    elif mutation == 'branch':
        pr['base']['ref'] = 'other'
    elif mutation == 'expired':
        task['expires_at'] = NOW.isoformat()
    elif mutation == 'revoked':
        task['state'] = 'REVOKED'
    else:
        task['task_id'] = 'other-task'
    with pytest.raises(guard.ScopeDenied, match=code):
        check(pr, task, changes)


def test_stale_source_and_symlink_cannot_pass():
    pr, task, changes = sample()
    with pytest.raises(guard.ScopeDenied, match='APPROVED_SOURCE_CHANGED'):
        check(pr, task, changes, blobs={'services/test.js': 'c' * 40})
    with pytest.raises(guard.ScopeDenied, match='NON_REGULAR'):
        check(pr, task, changes, modes={'services/test.js': '120000'})


@pytest.mark.parametrize('path', [
    '.github/agents/arkaon.agent.md', '.env', 'config/policy.json',
    'scripts/guard_github_worker.py', 'src/apf/improvement_permissions.py',
    'requests/github-coding/test-task.json',
])
def test_even_a_manifest_cannot_grant_control_changes(path):
    pr, task, changes = sample()
    task['allowed_paths'] = [path]
    task['expected_file_blobs'] = {path: 'b' * 40}
    changes[0]['filename'] = path
    with pytest.raises(guard.ScopeDenied, match='CONTROL_OR_SECRET'):
        check(pr, task, changes, modes={path: '100644'})


def test_explicitly_approved_new_regular_file_is_supported():
    pr, task, changes = sample()
    task['expected_file_blobs']['services/test.js'] = None
    changes[0]['status'] = 'added'
    assert check(pr, task, changes)['scope_passed']


def test_unrelated_human_pr_is_not_mislabeled_as_worker_execution():
    assert guard.task_id_for({'body': '', 'user': {'login': 'owner'}, 'head': {'ref': 'fix/ui'}}) is None
