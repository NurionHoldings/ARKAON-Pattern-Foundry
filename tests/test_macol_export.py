import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from apf.call_template import CallTemplateRequest
from apf.macol_export import export_macol


def request(**overrides: object) -> CallTemplateRequest:
    values = {
        "tenant_id": "tenant-a", "owner_id": "owner-a", "slug": "insuk-profile",
        "display_name": "홍길동", "introduction": "안녕하세요. 문의를 남겨주세요.",
        "purpose_prompts": ["제휴문의", "개발문의"],
    }
    return CallTemplateRequest(**(values | overrides))


def test_export_is_independent_and_runnable(tmp_path: Path) -> None:
    output = tmp_path / "macol-app"
    export_macol(request(), output)
    page = (output / "index.html").read_text(encoding="utf-8")
    assert 'value="홍길동"' in page
    assert "제휴문의&#10;개발문의&#10;개인적인 통화" in page
    assert "__MACOL_" not in page
    assert (output / "Dockerfile").is_file()
    assert (output / ".github/workflows/test.yml").is_file()
    assert json.loads((output / "manifest.webmanifest").read_text())["name"].endswith("홍길동의 전화응대")
    asset = json.loads((output / "template.json").read_text())
    assert asset["telephony_state"] == "NOT_CONNECTED"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "test_app.py"], cwd=output,
        env={**os.environ, "PYTHONPATH": str(output)}, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with pytest.raises(FileExistsError, match="OUTPUT_EXISTS"):
        export_macol(request(), output)


def test_export_refuses_unsupported_menu_contract(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="TOO_MANY_MENUS"):
        export_macol(request(purpose_prompts=[f"문의{i}" for i in range(8)]), tmp_path / "app")
    assert not (tmp_path / "app").exists()
    with pytest.raises(ValueError, match="PERSONAL_CALL_REQUIRES"):
        export_macol(request(purpose_prompts=["개인적인 통화"], allow_call_request=False),
                     tmp_path / "app")
