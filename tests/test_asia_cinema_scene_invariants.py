"""PR-B: fixed-camera scene invariants and approved A-symbol trace integrity."""
import copy
import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from asia_cinema.scene_invariants import check_snapshot

COMPANY = "ASIA HOLDINGS"
SLOGAN = "세상을 연결하는 가치, 더 큰 내일을 만듭니다"
SLOGAN_SHA = "e9cc11036d72e2b6216b118d1dce41e3abcf345be7d98cdcffd1b05e16bc19a8"
TRACE = ROOT / "modules" / "asia_cinema" / "config" / "a_symbol_trace.v1.json"
APPROVED_TRACE_SHA = "52f6b2201ac38ee4f0d503e0f2287c3b97d1ca32ed2473b74c9dc30f3d78bd31"


def _obj(parent=None, animated=(), **extra):
    return {"type": "MESH", "parent": parent, "animated_paths": list(animated), "drivers": [], "constraints": [], **extra}


def _good_snapshot() -> dict:
    return {
        "fps": 24,
        "frame_start": 1,
        "frame_end": 384,
        "camera": "CAM_Main",
        "objects": {
            "CAM_RIG": _obj(),
            "CAM_Main": _obj("CAM_RIG", data_animated_paths=[]),
            "GRP_Logo": _obj(),
            "A_Symbol_Metal": _obj("GRP_Logo"),
            "Globe": _obj("GRP_Logo", animated=["rotation_euler"]),
            "Orbit_Gold": _obj("GRP_Logo", animated=["rotation_euler"]),
            "TXT_Company": _obj("GRP_Logo", text_body=COMPANY),
            "TXT_Slogan_KO": _obj("GRP_Logo", text_body=SLOGAN),
            "BG_Plate": _obj("CAM_RIG"),
            "LIGHT_Key": _obj(),
        },
    }


def _codes(snapshot: dict) -> set[str]:
    report = check_snapshot(snapshot, company=COMPANY, slogan_sha256=SLOGAN_SHA)
    return {i["code"] for i in report["issues"]}


def test_valid_scene_passes():
    report = check_snapshot(_good_snapshot(), company=COMPANY, slogan_sha256=SLOGAN_SHA)
    assert report["ok"] is True
    assert report["issues"] == []


def test_camera_rig_keyframes_blocked():
    snap = _good_snapshot()
    snap["objects"]["CAM_RIG"]["animated_paths"] = ["location"]
    assert "TRANSFORM_KEYED" in _codes(snap)


def test_logo_group_and_background_keyframes_blocked():
    for name, path in (("GRP_Logo", "rotation_euler"), ("BG_Plate", "scale"), ("CAM_Main", "location")):
        snap = _good_snapshot()
        snap["objects"][name]["animated_paths"] = [path]
        assert "TRANSFORM_KEYED" in _codes(snap), name


def test_background_material_fade_is_allowed():
    snap = _good_snapshot()
    snap["objects"]["BG_Plate"]["animated_paths"] = ['nodes["Emission"].inputs[1].default_value']
    assert _codes(snap) == set()


def test_camera_lens_keyframes_and_constraints_blocked():
    snap = _good_snapshot()
    snap["objects"]["CAM_Main"]["data_animated_paths"] = ["lens"]
    snap["objects"]["CAM_RIG"]["constraints"] = ["FOLLOW_PATH"]
    assert {"CAMERA_DATA_KEYED", "CONSTRAINT"} <= _codes(snap)


def test_missing_object_and_wrong_parent_blocked():
    snap = _good_snapshot()
    del snap["objects"]["Globe"]
    snap["objects"]["BG_Plate"]["parent"] = "GRP_Logo"
    assert {"OBJECT_MISSING", "PARENT"} <= _codes(snap)


def test_text_tamper_blocked():
    snap = copy.deepcopy(_good_snapshot())
    snap["objects"]["TXT_Company"]["text_body"] = "ASIA HOLDING"
    snap["objects"]["TXT_Slogan_KO"]["text_body"] = SLOGAN + " "
    assert {"COMPANY_TEXT", "SLOGAN_TEXT"} <= _codes(snap)


def test_timeline_and_static_orbit_blocked():
    snap = _good_snapshot()
    snap["frame_end"] = 400
    snap["fps"] = 30
    snap["objects"]["Orbit_Gold"]["animated_paths"] = []
    assert {"FRAME_RANGE", "FPS", "NOT_ANIMATED"} <= _codes(snap)


def test_approved_trace_is_pinned_and_well_formed():
    raw = TRACE.read_bytes()
    assert sha256(raw).hexdigest() == APPROVED_TRACE_SHA, "trace changed without operator re-approval"
    data = json.loads(raw)
    w, h = data["canvas_px"]
    assert set(data["pieces"]) == {"a_top", "a_lower_left_blade", "a_lower_right_leg"}
    for name, pts in data["pieces"].items():
        assert len(pts) >= 3, name
        assert all(0 <= x <= w and 0 <= y <= h for x, y in pts), name
