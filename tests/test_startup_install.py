from pathlib import Path

import pytest

from apf.startup_install import build_startup_artifact, install_user_startup


@pytest.mark.parametrize("system", ["Linux", "Darwin", "Windows"])
def test_startup_artifacts_run_collector_at_user_login_without_elevation(system):
    artifact = build_startup_artifact(system, Path("/safe/collector.json"))
    assert "apf.collector_service" in artifact.content
    assert "collector.json" in artifact.content
    assert all(term not in artifact.content.lower() for term in ("sudo", "highestavailable"))


def test_linux_service_restarts_and_joins_default_user_target():
    artifact = build_startup_artifact("Linux", Path("/safe/collector.json"))
    assert "Restart=on-failure" in artifact.content
    assert "WantedBy=default.target" in artifact.content
    assert artifact.relative_path == Path("systemd/user/arkaon-collector.service")


def test_windows_task_is_least_privilege_and_single_instance():
    artifact = build_startup_artifact("Windows", Path("C:/ARKAON/collector.json"))
    assert "<RunLevel>LeastPrivilege</RunLevel>" in artifact.content
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in artifact.content


def test_installer_writes_only_below_explicit_user_config_root(tmp_path):
    config = tmp_path / "collector.json"
    config.write_text("{}", encoding="utf-8")
    root = tmp_path / "user-config"
    installed = install_user_startup(config, user_config_root=root, system="Linux")
    assert installed.is_relative_to(root)
    assert installed.exists()
    assert installed.stat().st_mode & 0o777 == 0o600


def test_unsupported_platform_fails_closed():
    with pytest.raises(ValueError, match="unsupported platform"):
        build_startup_artifact("Plan9", Path("collector.json"))
