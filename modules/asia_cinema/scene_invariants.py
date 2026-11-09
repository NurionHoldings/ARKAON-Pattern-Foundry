"""Fixed-camera invariants for the ASIA cinema scene (PR-B), independent of Blender.

The Blender-side collector (``blender/validate_scene_invariants.py``) turns a .blend into a plain
snapshot dict; this module decides pass/fail so the rules are unit-tested in CI without Blender.
"""
from __future__ import annotations

import hashlib
from typing import Any

FPS = 24
FRAME_START = 1
FRAME_END = 384
TRANSFORM_PATHS = frozenset({"location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"})
LOCKED_OBJECTS = ("CAM_RIG", "CAM_Main", "GRP_Logo", "BG_Plate")
REQUIRED_PARENTS = {
    "CAM_RIG": None,
    "CAM_Main": "CAM_RIG",
    "GRP_Logo": None,
    "A_Symbol_Metal": "GRP_Logo",
    "Globe": "GRP_Logo",
    "Orbit_Gold": "GRP_Logo",
    "TXT_Company": "GRP_Logo",
    "TXT_Slogan_KO": "GRP_Logo",
    "BG_Plate": "CAM_RIG",
    "LIGHT_Key": None,
}
MUST_ANIMATE = {"Globe": "rotation_euler", "Orbit_Gold": "rotation_euler"}


def _issue(code: str, message: str, obj: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "object": obj}


def check_snapshot(snapshot: dict[str, Any], *, company: str, slogan_sha256: str) -> dict[str, Any]:
    """Return a path-free report; ``ok`` is True only when every invariant holds."""
    issues: list[dict[str, Any]] = []
    objects: dict[str, Any] = snapshot.get("objects", {})

    if snapshot.get("fps") != FPS:
        issues.append(_issue("FPS", f"fps must be {FPS}"))
    if (snapshot.get("frame_start"), snapshot.get("frame_end")) != (FRAME_START, FRAME_END):
        issues.append(_issue("FRAME_RANGE", f"frame range must be {FRAME_START}-{FRAME_END}"))
    if snapshot.get("camera") != "CAM_Main":
        issues.append(_issue("ACTIVE_CAMERA", "scene camera must be CAM_Main"))

    for name, parent in REQUIRED_PARENTS.items():
        ob = objects.get(name)
        if ob is None:
            issues.append(_issue("OBJECT_MISSING", "required object missing", name))
            continue
        if ob.get("parent") != parent:
            issues.append(_issue("PARENT", f"parent must be {parent}", name))

    for name in LOCKED_OBJECTS:
        ob = objects.get(name)
        if ob is None:
            continue
        keyed = sorted(set(ob.get("animated_paths", [])) & TRANSFORM_PATHS)
        if keyed:
            issues.append(_issue("TRANSFORM_KEYED", f"transform keyframes forbidden: {', '.join(keyed)}", name))
        if ob.get("constraints"):
            issues.append(_issue("CONSTRAINT", "constraints forbidden on locked object", name))
        if ob.get("drivers"):
            issues.append(_issue("DRIVER", "drivers forbidden on locked object", name))

    cam = objects.get("CAM_Main", {})
    if cam.get("data_animated_paths"):
        issues.append(_issue("CAMERA_DATA_KEYED", "camera lens/data keyframes forbidden", "CAM_Main"))

    for name, path in MUST_ANIMATE.items():
        ob = objects.get(name)
        if ob is not None and path not in ob.get("animated_paths", []):
            issues.append(_issue("NOT_ANIMATED", f"{path} must be animated", name))

    company_body = objects.get("TXT_Company", {}).get("text_body")
    if company_body is not None and company_body != company:
        issues.append(_issue("COMPANY_TEXT", "TXT_Company does not match company_name_literal", "TXT_Company"))
    slogan_body = objects.get("TXT_Slogan_KO", {}).get("text_body")
    if slogan_body is not None:
        actual = hashlib.sha256(slogan_body.encode("utf-8")).hexdigest()
        if actual != slogan_sha256.lower():
            issues.append(_issue("SLOGAN_TEXT", "TXT_Slogan_KO does not match approved slogan sha256", "TXT_Slogan_KO"))

    return {
        "schema": "apf.asia-cinema-scene-invariants/v1",
        "ok": not issues,
        "issues": issues,
        "checked": {
            "fps": snapshot.get("fps"),
            "frame_range": [snapshot.get("frame_start"), snapshot.get("frame_end")],
            "locked_objects": list(LOCKED_OBJECTS),
            "object_count": len(objects),
        },
    }
