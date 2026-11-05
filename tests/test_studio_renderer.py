import shutil
import subprocess
from pathlib import Path

import pytest


def test_studio_renderer_security_content_and_themes():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime required for studio renderer checks")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, "--test", "tests/studio.test.cjs"], cwd=root, check=False,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
