"""Collect a snapshot of the ASIA cinema .blend and check fixed-camera invariants (PR-B).

  blender -b <scene.blend> -P modules/asia_cinema/blender/validate_scene_invariants.py -- \
      --manifest <pr-b manifest> --repo-root . --report <report.json>
Exit code 1 when any invariant fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_invariants import check_snapshot


def _args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--repo-root", type=Path, default=Path.cwd())
    p.add_argument("--report", type=Path, required=True)
    return p.parse_args(argv)


def _fcurves(anim_data) -> list:
    if anim_data is None or anim_data.action is None:
        return []
    action = anim_data.action
    try:
        curves = list(action.fcurves)
        if curves:
            return curves
    except (AttributeError, TypeError):
        pass
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                curves.extend(bag.fcurves)
    return curves


def snapshot() -> dict:
    scene = bpy.context.scene
    objects = {}
    for ob in scene.objects:
        anim = ob.animation_data
        entry = {
            "type": ob.type,
            "parent": ob.parent.name if ob.parent else None,
            "animated_paths": sorted({fc.data_path for fc in _fcurves(anim)}),
            "drivers": [d.data_path for d in anim.drivers] if anim else [],
            "constraints": [c.type for c in ob.constraints],
        }
        data_anim = getattr(ob.data, "animation_data", None) if ob.data is not None else None
        entry["data_animated_paths"] = sorted({fc.data_path for fc in _fcurves(data_anim)}) if ob.type == "CAMERA" else []
        if ob.type == "FONT":
            entry["text_body"] = ob.data.body
        objects[ob.name] = entry
    return {
        "fps": scene.render.fps,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "camera": scene.camera.name if scene.camera else None,
        "objects": objects,
    }


def main() -> None:
    a = _args()
    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    report = check_snapshot(
        snapshot(),
        company=manifest["company_name_literal"],
        slogan_sha256=manifest["slogan_ko"]["sha256"],
    )
    report["run_id"] = manifest["run_id"]
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("INVARIANTS_OK" if report["ok"] else "INVARIANTS_FAIL", json.dumps(report["issues"], ensure_ascii=False))
    if not report["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
