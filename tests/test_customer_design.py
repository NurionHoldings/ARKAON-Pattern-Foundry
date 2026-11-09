"""Verify the customer-facing design composer and export boundary."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_customer_design_composer() -> None:
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for design composer regressions')
    subprocess.run([node, 'tests/customer_design.cjs'],
                   cwd=Path(__file__).resolve().parents[1], check=True,
                   capture_output=True, text=True)
