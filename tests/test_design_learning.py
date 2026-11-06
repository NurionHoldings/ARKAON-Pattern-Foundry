import copy
import json

import pytest

from apf.design_learning import cycle, digest, evaluate, materialize, propose, validate_observation


def observation(*, reference=False):
    return {"schema_version": "apf.design-observation/v1",
            "source": {"url": "https://example.invalid/reference" if reference
                       else "http://localhost:8080/demo.html", "usage": "PRINCIPLES_ONLY",
                       "observed_at": "2026-11-06T00:00:00Z", "artifact_sha256": "a" * 64},
            "viewport": {"width": 390, "height": 844},
            "samples": [{"role": "body", "selector": ".own-body", "font_size_px": 18 if reference else 12,
                         "line_height": 1.6 if reference else 1.1, "gap_px": 24 if reference else 2,
                         "foreground": "#172033" if reference else "#aaaaaa", "background": "#ffffff",
                         "overflow_px": 0 if reference else 40}],
            "opportunities": ["새로운 결제 흐름과 독창적인 섹션 구성도 연구"]}


def candidate():
    return propose(observation(reference=True), observation(), target_css="services/demo.css")


def approval(proposal):
    return {"proposal_digest": proposal["proposal_digest"], "target_css": proposal["target_css"],
            "approver": "owner", "approved_at": "2026-11-06T01:00:00Z", "decision": "OWNER_APPROVED"}


def after(proposal):
    snap = observation()
    snap["applied_css_sha256"] = proposal["candidate_css_sha256"]
    snap["samples"][0].update(font_size_px=17, line_height=1.7, gap_px=20,
                              foreground="#172033", overflow_px=0)
    return snap


def difference():
    return {"user_purpose": "쉽게 읽고 문의", "original_composition": "독자적 안내 흐름",
            "beyond_color": "본문 크기·간격·줄바꿈 재구성", "evidence_ref": "review/run-1"}


def test_measured_gap_generates_own_css_and_retains_open_discovery():
    result = candidate()
    assert set(result["changes"][0]["criteria"]) == {
        "contrast", "text_size", "line_height", "spacing", "overflow"}
    assert "17px" in result["candidate_css"]
    assert "18px" not in result["candidate_css"]  # not copied reference sizing
    assert result["additional_opportunities"] == observation()["opportunities"]
    assert result["discovery_scope"] == "OPEN_ENDED"
    assert result["improvement_accepted"] is False


@pytest.mark.parametrize("field,value", [("font_size_px", float("nan")), ("line_height", True),
                                          ("foreground", "url(x)"), ("selector", ".x}body{")])
def test_untrusted_measurements_never_become_css(field, value):
    data = observation()
    data["samples"][0][field] = value
    with pytest.raises((ValueError, TypeError)):
        validate_observation(data)


@pytest.mark.parametrize("target", ["../private.css", "/tmp/x.css", "services/../x.css", "services/a.js"])
def test_paths_cannot_escape(target):
    with pytest.raises(ValueError):
        propose(observation(reference=True), observation(), target_css=target)


def test_css_materializes_only_exact_selection_approval_into_fresh_sandbox(tmp_path):
    proposal = candidate()
    wrong = approval(proposal) | {"proposal_digest": "b" * 64}
    with pytest.raises(ValueError):
        materialize(proposal, wrong, tmp_path)
    target = materialize(proposal, approval(proposal), tmp_path)
    assert target.read_text() == proposal["candidate_css"]
    with pytest.raises(FileExistsError):
        materialize(proposal, approval(proposal), tmp_path)


def test_tamper_rejected(tmp_path):
    proposal = candidate()
    proposal["candidate_css"] += "body {display:none}"
    with pytest.raises(ValueError):
        materialize(proposal, approval(proposal), tmp_path)


def test_objective_pass_still_requires_independent_visual_review():
    proposal = candidate()
    result = evaluate(proposal, after(proposal), differentiation=difference())
    assert result["automated_check_passed"] is True
    assert result["status"] == "INDEPENDENT_REVIEW_PENDING"
    assert result["improvement_accepted"] is False
    assert result["visual_review"] == "NOT_RUN"


def test_color_only_or_no_differentiation_does_not_pass_as_evolution():
    proposal = candidate()
    result = evaluate(proposal, after(proposal), differentiation={"beyond_color": "color"})
    assert result["status"] == "FOLLOWUP_REQUIRED"


def test_wrong_css_or_viewport_cannot_substitute_evidence():
    proposal = candidate()
    snap = after(proposal)
    snap["viewport"]["width"] = 1440
    with pytest.raises(ValueError):
        evaluate(proposal, snap, differentiation=difference())
    snap = after(proposal)
    snap["applied_css_sha256"] = "c" * 64
    with pytest.raises(ValueError):
        evaluate(proposal, snap, differentiation=difference())


def test_regressions_and_missing_fixes_produce_followup():
    proposal = candidate()
    snap = after(proposal)
    snap["samples"][0]["overflow_px"] = 60
    result = evaluate(proposal, snap, differentiation=difference())
    assert result["automated_check_passed"] is False
    assert result["status"] == "FOLLOWUP_REQUIRED"
    assert result["findings"]


def test_four_directions_require_selection_and_keep_bad_jobs_isolated(tmp_path):
    inbox = tmp_path / "inbox/design-learning"
    inbox.mkdir(parents=True)
    (inbox / "a.json").write_text("{broken")
    (inbox / "b.json").write_text(json.dumps({"reference": observation(reference=True),
                                            "baseline": observation(), "target_css": "services/demo.css"}))
    result = cycle(tmp_path)
    assert result["proposed"] == 1 and len(result["blocked"]) == 1
    path = next(p for p in (tmp_path / "state/design-learning").glob("*.json") if p.name != "latest.json")
    bundle = json.loads(path.read_text())
    assert len(bundle["choices"]) == 4
    assert len({c["candidate_css_sha256"] for c in bundle["choices"]}) == 4
    assert bundle["selection_required"] is True and bundle["automatic_selection_allowed"] is False
    assert "이 방향 선택" in path.with_suffix(".html").read_text()
    assert cycle(tmp_path)["duplicate"] == 2


def test_unchanged_good_baseline_does_not_claim_upgrade():
    base = observation(reference=True)
    assert propose(base, copy.deepcopy(base), target_css="services/demo.css")["status"] == "RESEARCH_REQUIRED"


def test_proposal_hash_is_stable():
    p = candidate()
    assert p["proposal_digest"] == digest({k: v for k, v in p.items() if k != "proposal_digest"})


def test_capability_gap_creates_existing_relay_compatible_improvement_request(tmp_path):
    from apf.self_improvement_relay import validate_request
    inbox = tmp_path / "inbox/design-learning"
    inbox.mkdir(parents=True)
    job = {"reference": observation(reference=True), "baseline": observation(),
           "target_css": "services/demo.css", "capability_comparisons": [
               {"capability": "자연어 요소 편집", "current": "수치 폼만 제공",
                "external": "문장으로 요소를 수정", "implementation_needed": "의도 해석과 요소 모델 연결",
                "acceptance": "관련 없는 필드 보존 및 undo 시험", "evidence_ref": "capture-1"}],
           "evidence": {"kind": "OFFICIAL_DOCUMENTATION", "provenance_complete": True,
                        "authorization_valid": True, "license_compatible": True, "consent_valid": True,
                        "independently_verified": False, "fresh": True, "contains_sensitive_data": False,
                        "confidence_percent": 80}}
    (inbox / "job.json").write_text(json.dumps(job))
    assert cycle(tmp_path)["blocked"] == []
    request_path = next((tmp_path / "inbox/self-improvement").glob("*.json"))
    request = json.loads(request_path.read_text())
    validate_request(request)
    assert "자연어 요소 편집" in request["capability_gap"]
    assert request["state"] == "INBOX_POSTED"
    assert request["source_tier"] == "PROPOSE_ONLY"
    assert request["automatic_merge_allowed"] is False
    assert cycle(tmp_path)["duplicate"] == 1


def test_unqualified_material_never_becomes_authorized_improvement(tmp_path):
    inbox = tmp_path / "inbox/design-learning"
    inbox.mkdir(parents=True)
    job = {"reference": observation(reference=True), "baseline": observation(),
           "target_css": "services/demo.css", "evidence": {"kind": "UNKNOWN"}}
    (inbox / "job.json").write_text(json.dumps(job))
    assert cycle(tmp_path)["blocked"]
    assert not (tmp_path / "inbox/self-improvement").exists()


def test_only_exact_direction_can_be_selected():
    from apf.design_learning import select_direction
    proposal = candidate()
    bundle = {"schema_version": "apf.design-direction-choices/v1", "choices": [proposal]}
    selection = {"schema_version": "apf.design-direction-selection/v1", "selected_at": "now",
                 "proposal_digest": proposal["proposal_digest"], "direction_id": "readable"}
    assert select_direction(bundle, selection) == proposal
    selection["direction_id"] = "compact"
    with pytest.raises(ValueError):
        select_direction(bundle, selection)


def test_bad_jobs_do_not_starve_later_jobs_over_multiple_cycles(tmp_path):
    inbox = tmp_path / "inbox/design-learning"
    inbox.mkdir(parents=True)
    for index in range(31):
        (inbox / f"{index:03}.json").write_text("broken-" + str(index))
    (inbox / "z.json").write_text(json.dumps({"reference": observation(reference=True),
        "baseline": observation(), "target_css": "services/demo.css"}))
    assert len(cycle(tmp_path)["blocked"]) == 30
    assert cycle(tmp_path)["proposed"] == 1


def test_standing_authority_builds_selected_candidate_without_new_approval(tmp_path):
    from pathlib import Path

    from apf.design_learning import delegated_sandbox
    policy = Path(__file__).parents[1] / "config/arkaon-design-evolution-policy.json"
    (tmp_path / "config").mkdir()
    (tmp_path / "config/arkaon-design-evolution-policy.json").write_bytes(policy.read_bytes())
    proposal = candidate()
    bundle = {"schema_version": "apf.design-direction-choices/v1", "choices": [proposal]}
    selection = {"schema_version": "apf.design-direction-selection/v1", "selected_at": "now",
                 "proposal_digest": proposal["proposal_digest"], "direction_id": "readable"}
    result = delegated_sandbox(tmp_path, bundle, selection)
    assert (tmp_path / result).read_text() == proposal["candidate_css"]
    assert delegated_sandbox(tmp_path, bundle, selection) == result
    (tmp_path / result).write_text("tampered")
    with pytest.raises(ValueError):
        delegated_sandbox(tmp_path, bundle, selection)


def test_delegation_cannot_turn_into_deployment_authority(tmp_path):
    from pathlib import Path

    from apf.design_learning import delegated_sandbox
    policy = json.loads((Path(__file__).parents[1] / "config/arkaon-design-evolution-policy.json").read_text())
    policy["deployment_allowed"] = True
    (tmp_path / "config").mkdir()
    (tmp_path / "config/arkaon-design-evolution-policy.json").write_text(json.dumps(policy))
    with pytest.raises(ValueError):
        delegated_sandbox(tmp_path, {}, {})


def test_collector_once_calls_design_learning_even_without_hourly_schedule(tmp_path, monkeypatch):
    from apf import collector_service
    runtime = type("Runtime", (), {"run_once": lambda self: object()})()
    calls = []
    monkeypatch.setattr(collector_service, "_build_runtime", lambda args: (runtime, None, tmp_path))
    monkeypatch.setattr(collector_service, "design_learning_cycle", calls.append)
    assert collector_service.main(["--config", "unused.json", "--once"]) == 0
    assert calls == [tmp_path]


def test_failed_candidate_is_returned_to_improvement_request(tmp_path):
    from apf.design_learning import DIRECTIONS
    inbox = tmp_path / "inbox/design-learning"
    inbox.mkdir(parents=True)
    proposal = candidate()
    snap = after(proposal)
    snap["samples"][0]["overflow_px"] = 90
    job = {"reference": observation(reference=True), "baseline": observation(),
           "target_css": "services/demo.css", "after": snap,
           "selection": {"schema_version": "apf.design-direction-selection/v1", "selected_at": "now",
                         "proposal_digest": proposal["proposal_digest"], "direction_id": next(iter(DIRECTIONS))},
           "differentiation": difference()}
    # No standing policy: feedback bundle is persisted, sandbox application remains blocked.
    (inbox / "job.json").write_text(json.dumps(job))
    result = cycle(tmp_path)
    assert result["blocked"]
    bundle = json.loads(next(p for p in (tmp_path / "state/design-learning").glob("*.json")
                             if p.name != "latest.json").read_text())
    assert bundle["evaluation"]["status"] == "FOLLOWUP_REQUIRED"
    assert bundle["evaluation"]["improvement_accepted"] is False
