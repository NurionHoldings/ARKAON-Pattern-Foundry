"""Read-only health evaluation for ARKAON autostart artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HealthCheck:
    check_id: str
    status: str
    detail: str


@dataclass(frozen=True)
class AutostartHealthReport:
    overall: str
    checks: tuple[HealthCheck, ...]
    issue_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "issue_codes": list(self.issue_codes),
            "checks": [
                {"check_id": item.check_id, "status": item.status, "detail": item.detail}
                for item in self.checks
            ],
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def evaluate_autostart_health(foundry_root: str | Path) -> AutostartHealthReport:
    root = Path(foundry_root).resolve()
    checks: list[HealthCheck] = []
    issues: list[str] = []

    collector_policy = root / "config" / "collector.default.json"
    if collector_policy.exists():
        raw = _read_json(collector_policy) or {}
        if raw.get("enabled") and raw.get("sources"):
            checks.append(HealthCheck("COLLECTOR_POLICY", "PASS", "enabled with sources"))
        else:
            checks.append(HealthCheck("COLLECTOR_POLICY", "FAIL", "enabled policy or sources missing"))
            issues.append("COLLECTOR_POLICY")
    else:
        checks.append(HealthCheck("COLLECTOR_POLICY", "FAIL", "collector.default.json missing"))
        issues.append("COLLECTOR_POLICY")

    required_scripts = (
        "orchestrator/arkaon-startup.ps1",
        "orchestrator/arkaon-collector-daemon.ps1",
        "orchestrator/arkaon-analysis-daemon.ps1",
        "orchestrator/arkaon-watchdog.ps1",
        "orchestrator/arkaon-autostart-diagnose.ps1",
        "orchestrator/arkaon-runtime.ps1",
    )
    missing_scripts = [relative for relative in required_scripts if not (root / relative).exists()]
    if missing_scripts:
        checks.append(
            HealthCheck("AUTOSTART_SCRIPTS", "FAIL", f"missing: {', '.join(missing_scripts)}")
        )
        issues.append("AUTOSTART_SCRIPTS")
    else:
        checks.append(HealthCheck("AUTOSTART_SCRIPTS", "PASS", "all required scripts present"))

    startup_state = _read_json(root / "state" / "startup-last-run.json")
    if startup_state and startup_state.get("completed_at"):
        checks.append(
            HealthCheck(
                "LAST_AUTOSTART",
                "PASS" if startup_state.get("status", "PASS") == "PASS" else "FAIL",
                f"observed={startup_state.get('observed_at')} status={startup_state.get('status', 'PASS')}",
            )
        )
        if startup_state.get("status") == "FAIL":
            issues.append("LAST_AUTOSTART")
    else:
        checks.append(HealthCheck("LAST_AUTOSTART", "WARN", "startup-last-run.json missing or incomplete"))

    for daemon_name in ("collector-daemon", "analysis-daemon"):
        status = _read_json(root / "state" / f"{daemon_name}.json")
        if status and status.get("pid") and status.get("started_at"):
            checks.append(
                HealthCheck(
                    daemon_name.upper().replace("-", "_"),
                    "PASS",
                    f"pid={status['pid']} started={status['started_at']}",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    daemon_name.upper().replace("-", "_"),
                    "WARN",
                    "daemon status file missing",
                )
            )

    audit_path = root / "state" / "arkaon-collection-audit.jsonl"
    if audit_path.exists() and audit_path.stat().st_size > 0:
        checks.append(HealthCheck("COLLECTION_AUDIT", "PASS", f"bytes={audit_path.stat().st_size}"))
    else:
        checks.append(HealthCheck("COLLECTION_AUDIT", "WARN", "no collection audit yet"))

    overall = "PASS" if not issues else "FAIL"
    return AutostartHealthReport(overall=overall, checks=tuple(checks), issue_codes=tuple(issues))


def report_as_json(foundry_root: str | Path) -> str:
    payload = evaluate_autostart_health(foundry_root).to_dict()
    payload["schema_version"] = "apf.autostart-health.v1"
    payload["checked_at"] = datetime.now(UTC).isoformat()
    return json.dumps(payload, ensure_ascii=False, indent=2)
