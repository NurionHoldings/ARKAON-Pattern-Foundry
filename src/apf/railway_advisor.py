"""Read-only Railway guidance from the reviewed experience playbook."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def guidance() -> dict[str, object]:
    playbook = json.loads(
        (ROOT / "knowledge/learning-playbooks/railway-activation.v1.json").read_text(
            encoding="utf-8",
        ),
    )
    readiness = json.loads(
        (ROOT / "knowledge/readiness/v0.1-readiness.json").read_text(
            encoding="utf-8",
        ),
    )
    allowed = readiness["locks"]["deployment"] is True
    phases = [
        {
            "id": phase["id"],
            "action": phase["action"],
            "proof": phase["proof"],
            "hold_when": phase["hold_when"],
        }
        for phase in playbook["phases"]
    ]
    return {
        "mode": "READ_ONLY_GUIDANCE",
        "overall_status": readiness["overall_status"],
        "deployment_allowed": allowed,
        "decision": "RECHECK_AND_HOLD" if not allowed else "RECHECK_BEFORE_ACTIVATION",
        "observation_date": "2026-09-24",
        "historical_observation": playbook["current_observation_2026_09_24"],
        "observation_is_live": False,
        "next_action": (
            "Recheck Railway and GitHub current state, exact PR head/CI and pending changes; "
            "keep Apply/Deploy blocked while deployment=false."
            if not allowed else
            "Recheck provider evidence and obtain the reviewed activation scope before Apply/Deploy."
        ),
        "phases": phases,
        "automated_railway_write": False,
    }
