"""Read-only PR scope review. Never check out or execute the submitted code."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

TASK_LINE = re.compile(r"^ARKAON_TASK: ([a-z0-9][a-z0-9-]{0,79})\s*$", re.MULTILINE)
BOT_LOGINS = frozenset({'copilot-swe-agent[bot]', 'copilot-swe-agent', 'copilot'})
CONTROL_FILES = frozenset({
    'scripts/guard_github_worker.py', 'scripts/build_static.py', 'netlify.toml',
    'src/apf/improvement_permissions.py', 'src/apf/worker_runtime.py',
    'src/apf/execution_sandbox.py', 'src/apf/development_orchestrator.py',
    'src/apf/console.py', 'src/apf/self_improvement_execution.py',
})


class ScopeDenied(ValueError):
    pass


def task_id_for(pr: dict) -> str | None:
    body = pr.get('body') or ''
    matches = TASK_LINE.findall(body)
    actor = (pr.get('user') or {}).get('login', '').casefold()
    required = actor in BOT_LOGINS or (pr.get('head') or {}).get('ref', '').startswith('arkaon/')
    if not matches and not required:
        return None
    if len(matches) != 1:
        raise ScopeDenied('EXACTLY_ONE_ARKAON_TASK_REQUIRED')
    return matches[0]


def _safe_path(path: str) -> bool:
    value = PurePosixPath(path)
    return bool(path) and '\\' not in path and not value.is_absolute() and '..' not in value.parts


def check_scope(pr: dict, task: dict, changes: list[dict], *, now: datetime,
                base_blobs: dict[str, str], head_modes: dict[str, str]) -> dict:
    task_id = task_id_for(pr)
    if not task_id or task.get('task_id') != task_id:
        raise ScopeDenied('TASK_BINDING_MISMATCH')
    if task.get('schema_version') != 'apf.github-coding-task/v1':
        raise ScopeDenied('TASK_SCHEMA_INVALID')
    if task.get('state') != 'APPROVED_FOR_ONE_TASK':
        raise ScopeDenied('TASK_NOT_APPROVED')
    if now.tzinfo is None:
        raise ScopeDenied('TIMEZONE_REQUIRED')
    try:
        expiry = datetime.fromisoformat(task['expires_at'])
        if expiry.tzinfo is None or now >= expiry:
            raise ScopeDenied('TASK_EXPIRED')
    except (KeyError, ValueError, TypeError) as exc:
        if isinstance(exc, ScopeDenied):
            raise
        raise ScopeDenied('TASK_EXPIRY_INVALID') from None
    actor = (pr.get('user') or {}).get('login', '').casefold()
    if actor not in {value.casefold() for value in task.get('allowed_actors', [])}:
        raise ScopeDenied('WORKER_ACTOR_MISMATCH')
    base, head = pr.get('base') or {}, pr.get('head') or {}
    if base.get('ref') != task.get('base_branch'):
        raise ScopeDenied('BASE_BRANCH_MISMATCH')
    if (head.get('repo') or {}).get('full_name') != task.get('repository'):
        raise ScopeDenied('HEAD_REPOSITORY_MISMATCH')
    allowed = set(task.get('allowed_paths', []))
    if not allowed or any(not _safe_path(path) for path in allowed):
        raise ScopeDenied('TASK_SCOPE_INVALID')
    if not changes or len(changes) > task.get('max_changed_files', 0):
        raise ScopeDenied('CHANGE_COUNT_EXCEEDED')
    if sum(item.get('additions', 0) + item.get('deletions', 0) for item in changes) > task.get('max_changed_lines', 0):
        raise ScopeDenied('CHANGE_BUDGET_EXCEEDED')
    protected = {'.github', 'config', 'approvals', 'secrets', 'private', 'customer-data'}
    for item in changes:
        filename = item.get('filename', '')
        previous = item.get('previous_filename', filename)
        if not _safe_path(filename) or filename not in allowed or previous not in allowed:
            raise ScopeDenied('OUT_OF_SCOPE_CHANGE')
        if any(part.casefold() in protected or part.casefold().startswith('.env')
               for part in PurePosixPath(filename).parts) or filename in CONTROL_FILES \
                or filename.startswith('requests/github-coding/'):
            raise ScopeDenied('CONTROL_OR_SECRET_CHANGE')
        if item.get('status') == 'removed':
            raise ScopeDenied('FILE_DELETION_NOT_APPROVED')
        if head_modes.get(filename) != '100644':
            raise ScopeDenied('NON_REGULAR_FILE_CHANGE')
    expected = task.get('expected_file_blobs') or {}
    if set(expected) != allowed or any(base_blobs.get(path) != sha for path, sha in expected.items()):
        raise ScopeDenied('APPROVED_SOURCE_CHANGED')
    return {'enforced': True, 'task_id': task_id, 'head_sha': head.get('sha'),
            'changed_files': [item['filename'] for item in changes], 'scope_passed': True}


def main() -> int:
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    pr = event.get('pull_request')
    if not pr:
        raise ScopeDenied('PULL_REQUEST_EVENT_REQUIRED')
    task_id = task_id_for(pr)
    if task_id is None:
        print(json.dumps({'enforced': False, 'reason': 'NOT_ARKAON_TASK'}))
        return 0
    repository = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ScopeDenied('REPOSITORY_INVALID')
    token = os.environ['GH_TOKEN']

    def get(path: str):
        request = urllib.request.Request('https://api.github.com/' + path, headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ScopeDenied('API_RESPONSE_TOO_LARGE')
        return json.loads(raw)

    current = get(f'repos/{repository}/pulls/{pr["number"]}')
    if current['head']['sha'] != pr['head']['sha']:
        raise ScopeDenied('HEAD_MOVED_RERUN_REQUIRED')
    branch = event['repository']['default_branch']
    from urllib.parse import quote
    content = get(f'repos/{repository}/contents/requests/github-coding/{task_id}.json?ref={quote(branch, safe="")}')
    task = json.loads(base64.b64decode(content['content']))
    if task.get('repository') != repository:
        raise ScopeDenied('TASK_REPOSITORY_MISMATCH')
    issue = get(f'repos/{repository}/issues/{int(task["issue_number"])}')
    if issue.get('state') != 'open' or task_id_for({'body': issue.get('body')}) != task_id:
        raise ScopeDenied('ISSUE_NOT_ACTIVE_OR_MISMATCHED')
    changes = []
    for page in range(1, 32):
        batch = get(f'repos/{repository}/pulls/{pr["number"]}/files?per_page=100&page={page}')
        changes.extend(batch)
        if len(changes) > task['max_changed_files'] or len(batch) < 100:
            break
    blobs = {}
    for path in task['allowed_paths']:
        try:
            file = get(f'repos/{repository}/contents/{quote(path, safe="/")}?ref={pr["base"]["sha"]}')
            blobs[path] = file['sha']
        except urllib.error.HTTPError as error:
            if error.code != 404 or task['expected_file_blobs'].get(path, 'missing') is not None:
                raise
            blobs[path] = None
    tree = get(f'repos/{repository}/git/trees/{pr["head"]["sha"]}?recursive=1')
    if tree.get('truncated'):
        raise ScopeDenied('HEAD_TREE_TRUNCATED')
    modes = {item['path']: item['mode'] for item in tree['tree']}
    result = check_scope(pr, task, changes, now=datetime.now(UTC), base_blobs=blobs, head_modes=modes)
    print(json.dumps(result, ensure_ascii=False))
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a') as stream:
            stream.write('ARKAON scope review passed for ' + result['head_sha'] + '\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ScopeDenied, KeyError, TypeError, ValueError, urllib.error.URLError) as error:
        print(json.dumps({'scope_passed': False, 'reason': str(error) if isinstance(error, ScopeDenied)
                          else type(error).__name__}))
        raise SystemExit(1) from None
