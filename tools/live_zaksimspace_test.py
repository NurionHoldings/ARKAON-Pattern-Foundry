"""One-shot live test: zaksimspace.co.kr structural observation + analysis target resolution."""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

FOUNDRY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDRY / "src"))

from apf.analysis_target_resolution import AnalysisTargetResolutionEngine
from apf.analysis_target_resolution_bridge import bridge_analysis_target_resolution_report
from apf.central_orchestrator import CentralOrchestrator
from apf.structural_surface_common import digest_document, structural_signals_from_public_html

URL = "https://zaksimspace.co.kr/"


def main() -> int:
    now = datetime.now(UTC)
    request = urllib.request.Request(URL, headers={"User-Agent": "ARKAON-Pattern-Foundry/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read(500_000)

    signals = structural_signals_from_public_html(payload, context="zaksimspace")
    text = payload.decode("utf-8", errors="replace")
    flow_markers: list[str] = []
    if re.search(r"step\s*1|step\s*2|step\s*3|step\s*4", text, re.I):
        flow_markers.extend(
            [
                "flow/step-select",
                "flow/step-info-payment",
                "flow/step-e-contract",
                "flow/step-complete",
            ]
        )
    if re.search(r"전자|계약|esign|sign", text, re.I):
        flow_markers.append("flow/electronic-contract")
    if re.search(r"비교|comparison|others", text, re.I):
        flow_markers.append("surface/comparison-matrix")
    if re.search(r"마이페이지|dashboard|대시보드", text, re.I):
        flow_markers.append("surface/mypage-dashboard")
    if re.search(r"faq|자주하는\s*질문", text, re.I):
        flow_markers.append("surface/faq-accordion")
    policy_routes = tuple(sorted(set(flow_markers)))

    observation = {
        "schema_version": "apf.public-surface-observation/v1",
        "platform_id": "ZAKSIMSPACE",
        "observed_at": now.isoformat(),
        "rights_posture": "PUBLIC_OBSERVATION",
        "source_url": URL,
        "openapi_paths": [],
        "policy_route_refs": list(policy_routes),
        "js_structures": [],
        "observation_signals": signals,
        "observation_digest": "",
        "copy_prohibited": True,
        "verbatim_storage": False,
        "maximum_outcome": "STRUCTURAL_OBSERVATION",
    }
    observation["observation_digest"] = digest_document(
        {key: value for key, value in observation.items() if key != "observation_digest"}
    )
    store = FOUNDRY / "state" / "surface-observations"
    store.mkdir(parents=True, exist_ok=True)
    observation_path = store / f"zaksimspace-{observation['observation_digest'][:12]}.json"
    observation_path.write_text(
        json.dumps(observation, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    engine = AnalysisTargetResolutionEngine(foundry_root=FOUNDRY)
    report = engine.analyze(
        now=now,
        run_id="live-zaksimspace-test",
        dry_run=False,
        enabled_registration_count=1,
        enabled_paths_missing=False,
        registered_platform_ids=frozenset({"NARANG_RIDER"}),
        all_platforms_blocked=False,
    )
    packet_paths = bridge_analysis_target_resolution_report(
        foundry_root=FOUNDRY,
        report=report,
        policy=engine.policy,
        run_id="live-zaksimspace-test",
        now=now,
        dry_run=False,
    )

    orchestrator = CentralOrchestrator.from_config(FOUNDRY)
    registrations = CentralOrchestrator.load_platforms(
        FOUNDRY / "config" / "platforms.json",
        foundry_root=FOUNDRY,
    )
    orchestrator_report = orchestrator.run(registrations, dry_run=True)

    print("=== ZAKSIMSPACE LIVE TEST ===")
    print("fetch_bytes:", len(payload))
    print("structural_signals:", json.dumps(signals, ensure_ascii=False))
    print("policy_route_refs:", policy_routes)
    print("surface_observation:", observation_path.relative_to(FOUNDRY).as_posix())
    print("--- analysis target resolution ---")
    print("ambiguous:", report.ambiguous, report.ambiguity_reason)
    if report.last_user_site:
        print("last_site:", report.last_user_site.platform_id)
        print("sought_tokens:", list(report.last_user_site.sought_capability_tokens))
    print("cross_platform_targets:", [item.platform_id for item in report.targets])
    for target in report.targets:
        print(" ", target.platform_id, "->", list(target.capability_tokens))
    print("research_packets:", packet_paths)
    print("--- orchestrator dry-run ---")
    print("inbox_packets:", len(orchestrator_report.inbox_packets))
    cross_platform = [path for path in orchestrator_report.inbox_packets if "cross-platform" in path]
    print("cross_platform_in_run:", cross_platform)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
