"""Exercise mailbox report and clipboard behavior without an API session."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_mailbox_review_report() -> None:
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for mailbox client regressions')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([node, 'tests/mailbox_report.cjs'], cwd=root, check=True,
                   capture_output=True, text=True)
