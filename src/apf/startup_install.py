from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StartupArtifact:
    platform: str
    relative_path: Path
    content: str


def collector_command(config_path: Path, *, posix_paths: bool = False) -> tuple[str, ...]:
    data_dir = config_path.parent
    path_for = _posix_path if posix_paths else str
    return (
        sys.executable,
        "-m",
        "apf.collector_service",
        "--config",
        path_for(config_path),
        "--audit",
        path_for(data_dir / "arkaon-collection-audit.jsonl"),
        "--state",
        path_for(data_dir / "arkaon-collection-state.sqlite3"),
    )


def build_startup_artifact(system: str, config_path: Path) -> StartupArtifact:
    normalized = system.lower()
    if normalized == "linux":
        command = collector_command(config_path, posix_paths=True)
        exec_start = " ".join(_systemd_quote(part) for part in command)
        return StartupArtifact(
            platform="linux",
            relative_path=Path("systemd/user/arkaon-collector.service"),
            content=(
                "[Unit]\nDescription=ARKAON continuous collector\nAfter=network-online.target\n\n"
                "[Service]\nType=simple\nRestart=on-failure\nRestartSec=30\n"
                f"WorkingDirectory={_systemd_quote(_posix_path(config_path.parent))}\n"
                f"ExecStart={exec_start}\n\n[Install]\nWantedBy=default.target\n"
            ),
        )
    if normalized == "darwin":
        command = collector_command(config_path, posix_paths=True)
        arguments = "\n".join(f"      <string>{_xml_escape(part)}</string>" for part in command)
        return StartupArtifact(
            platform="darwin",
            relative_path=Path("LaunchAgents/com.nurion.arkaon.collector.plist"),
            content=(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict>\n'
                "  <key>Label</key><string>com.nurion.arkaon.collector</string>\n"
                "  <key>ProgramArguments</key><array>\n"
                f"{arguments}\n"
                "  </array>\n  <key>RunAtLoad</key><true/>\n"
                f"  <key>WorkingDirectory</key><string>{_xml_escape(_posix_path(config_path.parent))}</string>\n"
                "  <key>KeepAlive</key><true/>\n</dict></plist>\n"
            ),
        )
    command = collector_command(config_path)
    if normalized == "windows":
        executable, *arguments = command
        argument_text = " ".join(_windows_quote(part) for part in arguments)
        return StartupArtifact(
            platform="windows",
            relative_path=Path("ARKAON/arkaon-collector-task.xml"),
            content=(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
                "  <Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers>\n"
                "  <Principals><Principal id=\"Author\"><LogonType>InteractiveToken</LogonType>"
                "<RunLevel>LeastPrivilege</RunLevel></Principal></Principals>\n"
                "  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
                "<RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>"
                "</Settings>\n"
                f"  <Actions Context=\"Author\"><Exec><Command>{_xml_escape(executable)}</Command>"
                f"<Arguments>{_xml_escape(argument_text)}</Arguments>"
                f"<WorkingDirectory>{_xml_escape(str(config_path.parent))}</WorkingDirectory>"
                "</Exec></Actions>\n"
                "</Task>\n"
            ),
        )
    raise ValueError(f"unsupported platform: {system}")


def install_user_startup(
    config_path: str | Path,
    *,
    user_config_root: str | Path,
    system: str | None = None,
) -> Path:
    config = Path(config_path).expanduser().resolve(strict=True)
    artifact = build_startup_artifact(system or platform.system(), config)
    destination = Path(user_config_root).expanduser().resolve() / artifact.relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(artifact.content, encoding="utf-8")
    if os.name != "nt":
        destination.chmod(0o600)
    return destination


def _posix_path(path: Path) -> str:
    return path.as_posix()


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _windows_quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
