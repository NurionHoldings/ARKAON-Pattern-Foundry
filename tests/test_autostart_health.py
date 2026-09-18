import json
from pathlib import Path

from apf.autostart_health import evaluate_autostart_health, report_as_json


def test_autostart_health_passes_for_current_repo():
    report = evaluate_autostart_health(Path("."))
    assert report.overall == "PASS"
    check_ids = {item.check_id for item in report.checks}
    assert "COLLECTOR_POLICY" in check_ids
    assert "AUTOSTART_SCRIPTS" in check_ids


def test_autostart_health_json_is_serializable():
    payload = json.loads(report_as_json(Path(".")))
    assert payload["schema_version"] == "apf.autostart-health.v1"
    assert payload["overall"] in {"PASS", "FAIL", "WARN"}
