import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.predeployment_readiness import (
    CheckStatus,
    PredeploymentReadinessHarness,
    PredeployRejected,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _mini_foundry(tmp_path: Path) -> Path:
    root = tmp_path / "foundry"
    for folder in ("config", "inbox/research", "inbox/eternian-review", "inbox/operator-decision", "state"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    for name in (
        "shared-policy.json",
        "resource-limits.json",
        "platforms.json",
        "arkaon-admin-change-control.json",
        "arkaon-public-surface-observation.json",
        "arkaon-research-watch.json",
        "research-watch-sources.json",
        "arkaon-reflective-learning-policy.json",
        "arkaon-experience-operations-audit.json",
        "arkaon-predeployment-readiness.json",
        "arkaon-mobility-plaza-governance.json",
        "arkaon-map-ops-gate.json",
        "map-competency-profile.json",
        "map-provider-knowledge.provisional.json",
    ):
        (root / "config" / name).write_text(
            (FOUNDRY / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    document = json.loads((root / "config" / "platforms.json").read_text(encoding="utf-8"))
    document["foundry_root"] = str(root)
    (root / "config" / "platforms.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def test_predeployment_harness_passes_with_complete_foundry(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    report = PredeploymentReadinessHarness(foundry_root=root).run(now=NOW)
    assert report.overall is CheckStatus.PASS
    assert any(item.check_id == "PUBLIC_SURFACE_POLICY" and item.status is CheckStatus.PASS for item in report.results)


def test_predeployment_fails_closed_when_shared_policy_forbidden(tmp_path: Path) -> None:
    root = _mini_foundry(tmp_path)
    policy_path = root / "config" / "shared-policy.json"
    document = json.loads(policy_path.read_text(encoding="utf-8"))
    document["automatic_learning"] = True
    policy_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(PredeployRejected, match="mandatory predeployment checks failed"):
        PredeploymentReadinessHarness(foundry_root=root).run(now=NOW)
