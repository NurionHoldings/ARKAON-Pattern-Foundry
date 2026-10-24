"""Run vector escaping and rendering checks alongside the Python CI suite."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_brand_studio_node_suite():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is unavailable')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([node, '--test', 'tests/brand-studio.test.cjs'], cwd=root, check=True)
