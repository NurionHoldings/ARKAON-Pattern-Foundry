import subprocess
from pathlib import Path

from apf.api import runtime_root

ROOT = Path(__file__).parents[1]


def test_owner_artifact_paths_are_ignored_and_default_runtime_is_not_repo(monkeypatch):
    monkeypatch.delenv("APF_RUNTIME_ROOT", raising=False)
    assert runtime_root().resolve() != ROOT.resolve()
    for path in ("state/business-cards/example.json", "state/logo-drafts/example.json"):
        result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
        assert result.returncode == 0


def test_runtime_root_is_required_in_production(monkeypatch):
    monkeypatch.setenv("APF_ENV", "production")
    monkeypatch.delenv("APF_RUNTIME_ROOT", raising=False)
    try:
        runtime_root()
    except RuntimeError as error:
        assert str(error) == "APF_RUNTIME_ROOT is required in production"
    else:
        raise AssertionError("production runtime root must be explicit")
