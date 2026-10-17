import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apf.api import create_app
from apf.care_facility_design import (
    CareDesignRequest,
    CareFacilityBrief,
    build_care_design_packet,
)
from apf.console import ConsoleSecurity
from apf.repository import MemoryRepository

ROOT = Path(__file__).parents[1]


def sample():
    return json.loads((ROOT / "examples/thearirang-care-49-brief.json").read_text())


def packet(document, confirmed=None, **kwargs):
    return build_care_design_packet(CareDesignRequest.model_validate({
        "brief": document, "confirmed_digest": confirmed, **kwargs,
    }))


def test_approved_program_arithmetic_and_confirmation():
    request = sample()
    first = packet(request)
    assert (first["room_count"], first["computed_residents"], first["ensuite_wc_count"]) == (22, 49, 22)
    assert first["kitchen_m2"] == 49.59
    assert first["known_budget_m2"] == 1267.59
    assert first["area_difference_m2"] is None
    assert first["image_prompt"] is None
    ready = packet(request, first["brief_digest"])
    assert ready["status"] == "PROPOSAL_PACKET_READY"
    assert "1-resident bedroom x 7" in ready["image_prompt"]
    assert "staff_rest" in ready["image_prompt"]
    assert ready["legal_compliance"] == ready["measured_fit"] == "NOT_VERIFIED"
    assert not ready["automatic_generation"] and not ready["production_change_allowed"]


def test_56_person_conflict_never_silently_changes_rooms():
    request = sample()
    request["room_types"][2]["count"] = request["room_types"][3]["count"] = 5
    original = copy.deepcopy(request)
    result = packet(request)
    assert result["computed_residents"] == 56
    assert result["blockers"][0]["code"] == "CAPACITY_MISMATCH"
    assert result["image_prompt"] is None
    assert request == original


def test_changed_requirements_and_order_independent_digest():
    request = sample()
    before = packet(request)
    request["room_types"].reverse()
    request["support_spaces"].reverse()
    assert packet(request)["brief_digest"] == before["brief_digest"]
    request["kitchen_pyeong"] = 16
    result = packet(request, before["brief_digest"])
    assert result["status"] == "CONFIRMATION_STALE"
    assert result["image_prompt"] is None


def test_wc_staff_and_bathing_cannot_be_silently_omitted():
    request = sample()
    request["room_types"][0]["ensuite_wc"] = False
    request["room_types"][0]["toilet_target_m2"] = None
    request["support_spaces"] = [s for s in request["support_spaces"]
                                 if s["kind"] not in {"staff_rest", "staff_changing", "female_bathing"}]
    result = packet(request)
    assert {b["code"] for b in result["blockers"]} == {"ENSUITE_MISSING", "SPACE_REVIEW_REQUIRED"}
    assert result["ensuite_wc_count"] == 15


@pytest.mark.parametrize("value", [True, -1, 0, 4.5, "7"])
def test_counts_are_bounded_strict_integers(value):
    request = sample()
    request["room_types"][0]["count"] = value
    with pytest.raises(ValidationError):
        CareFacilityBrief.model_validate(request)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), -1, 0])
def test_area_is_finite_and_positive(value):
    request = sample()
    request["kitchen_pyeong"] = value
    with pytest.raises(ValidationError):
        CareFacilityBrief.model_validate(request)


def test_duplicate_categories_unknown_fields_and_inconsistent_toilet_rejected():
    for change in ["room", "space", "extra", "toilet"]:
        request = sample()
        if change == "room":
            request["room_types"][1]["occupancy"] = 1
        elif change == "space":
            request["support_spaces"].append(request["support_spaces"][0])
        elif change == "extra":
            request["legal_compliance"] = True
        else:
            request["room_types"][0]["ensuite_wc"] = False
        with pytest.raises(ValidationError):
            CareFacilityBrief.model_validate(request)


def test_budget_fit_never_certifies_geometry_and_missing_areas_are_unknown():
    request = sample()
    request["available_area_m2"] = 1322.31
    result = packet(request)
    assert result["area_difference_m2"] == 54.72
    assert result["measured_fit"] == "NOT_VERIFIED"
    request["available_area_m2"] = 1200
    assert any(b["code"] == "AREA_BUDGET_EXCEEDED" for b in packet(request)["blockers"])
    request["room_types"][0]["bedroom_target_m2"] = None
    result = packet(request)
    assert not result["area_budget_complete"]
    assert result["area_difference_m2"] is None
    request["available_area_m2"] = 1000
    assert any(b["code"] == "AREA_BUDGET_EXCEEDED" for b in packet(request)["blockers"])


def test_scene_specific_prompts_and_single_bedroom_are_distinct():
    request = sample()
    digest = packet(request)["brief_digest"]
    for scene in ["overview", "bedroom", "staff_support", "kitchen_bathing"]:
        result = packet(request, digest, scene=scene, bedroom_occupancy=3)
        assert result["status"] == "PROPOSAL_PACKET_READY"
        if scene == "bedroom":
            assert "exactly 3 beds" in result["image_prompt"]
    request["room_types"] = [{"occupancy": 1, "count": 49}]
    digest = packet(request)["brief_digest"]
    result = packet(request, digest, scene="bedroom", bedroom_occupancy=2)
    assert result["blockers"][-1]["code"] == "BEDROOM_TYPE_NOT_REQUESTED"


def client():
    app = create_app(repository=MemoryRepository(), console_security=ConsoleSecurity(
        environment="test", secret="s" * 32, allow_dev_sessions=True,
    ))
    return TestClient(app, base_url="https://testserver")


def test_console_auth_csrf_role_and_no_store():
    c = client()
    request = {"brief": sample()}
    assert c.get("/console/care-facility").status_code == 401
    assert c.post("/v1/console/care-facility/plan", json=request).status_code == 401
    def login(role):
        return c.post("/console/dev/session", json={"tenant_id": str(uuid4()),
                      "principal_id": str(uuid4()), "role": role}).json()["csrf_token"]
    csrf = login("operator")
    assert c.get("/console/care-facility").headers["Cache-Control"] == "no-store"
    assert c.post("/v1/console/care-facility/plan", json=request).status_code == 403
    response = c.post("/v1/console/care-facility/plan", json=request,
                      headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    digest = response.json()["brief_digest"]
    request["confirmed_digest"] = digest
    ready = c.post("/v1/console/care-facility/plan", json=request,
                   headers={"X-CSRF-Token": csrf})
    assert ready.json()["status"] == "PROPOSAL_PACKET_READY"
    csrf = login("auditor")
    assert c.post("/v1/console/care-facility/plan", json=request,
                  headers={"X-CSRF-Token": csrf}).status_code == 403
