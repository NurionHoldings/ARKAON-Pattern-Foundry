from __future__ import annotations

import base64
import hashlib
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_public_bundle_excludes_runtime_and_hashes_each_script() -> None:
    module = runpy.run_path(str(ROOT / 'scripts' / 'build_static.py'))
    module['build'](ROOT / 'dist')
    bundle = ROOT / 'dist'
    headers = (bundle / '_headers').read_text()
    for private in ('src', 'inbox', 'state', 'approvals', 'evidence', '.git', 'pyproject.toml'):
        assert not (bundle / private).exists()
    assert sorted(p.name for p in (bundle / 'config').iterdir()) == [
        'arkaon-home-services.json', 'arkaon-public-api.json',
    ]
    assert "script-src 'self'" in headers
    assert "script-src 'self' 'unsafe-inline'" not in headers
    assert "frame-ancestors 'none'" in headers
    for page in bundle.rglob('*.html'):
        parser = module['ScriptHashes']()
        parser.feed(page.read_text())
        for script_hash in parser.hashes:
            assert script_hash in headers
    parser = module['ScriptHashes']()
    parser.feed('<script>const a = "<p>& hello";</script>')
    digest = base64.b64encode(hashlib.sha256(b'const a = "<p>& hello";').digest()).decode()
    assert parser.hashes == {f"'sha256-{digest}'"}


def test_client_security_regressions() -> None:
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for client security regressions')
    subprocess.run([node, str(ROOT / 'tests' / 'static_services_security.cjs')],
                   cwd=ROOT, check=True, capture_output=True, text=True)
