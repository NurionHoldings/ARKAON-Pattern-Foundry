import json
from pathlib import Path

from apf.autostart_health import evaluate_autostart_health, report_as_json


def test_autostart_health_reports_daemon_and_policy_checks():
    report = evaluate_autostart_health(Path("."))
    assert report.overall in {"PASS", "FAIL"}
    check_ids = {item.check_id for item in report.checks}
    assert "COLLECTOR_POLICY" in check_ids
    assert "AUTOSTART_SCRIPTS" in check_ids
    assert "COLLECTOR_DAEMON" in check_ids
    assert "ANALYSIS_DAEMON" in check_ids


def test_autostart_health_json_is_serializable():
    payload = json.loads(report_as_json(Path(".")))
    assert payload["schema_version"] == "apf.autostart-health.v1"
    assert payload["overall"] in {"PASS", "FAIL", "WARN"}
