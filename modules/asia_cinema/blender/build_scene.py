"""Build the ASIA HOLDINGS fixed-camera cinema scene (PR-B) inside Blender.

Run only after the PR-A validator passed on the same manifest:
  blender -b --factory-startup -P modules/asia_cinema/blender/build_scene.py -- \
      --manifest <pr-b manifest> --repo-root . --out-blend <path.blend>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy

FPS = 24
FRAME_START = 1
FRAME_END = 384
SYMBOL_HEIGHT = 2.0
LOGO_LIFT = 0.45
REQUIRED_ASSETS = ("asia_a_symbol_trace", "asia_bg_plate", "font_en", "font_ko")


def _args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--repo-root", type=Path, default=Path.cwd())
    p.add_argument("--out-blend", type=Path, required=True)
    return p.parse_args(argv)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_inputs(manifest_path: Path, repo_root: Path) -> dict:
    """Re-check pinned hashes inside Blender so a swapped file can never reach the scene."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = {a["id"]: a for a in manifest["assets"]}
    resolved: dict[str, Path] = {}
    for aid in REQUIRED_ASSETS:
        if aid not in assets:
            raise SystemExit(f"manifest missing asset: {aid}")
        p = Path(assets[aid]["path"])
        p = p if p.is_absolute() else (repo_root / p).resolve()
        if _sha256(p) != assets[aid]["sha256"].lower():
            raise SystemExit(f"sha256 mismatch: {aid}")
        resolved[aid] = p
    slogan = manifest["slogan_ko"]
    slogan_path = Path(slogan["path"])
    slogan_path = slogan_path if slogan_path.is_absolute() else (repo_root / slogan_path).resolve()
    raw = slogan_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != slogan["sha256"].lower():
        raise SystemExit("sha256 mismatch: slogan_ko")
    return {
        "paths": resolved,
        "company": manifest["company_name_literal"],
        "slogan": raw.decode("utf-8"),
        "run_id": manifest["run_id"],
    }


def _principled(name: str, base, metallic: float, roughness: float, emission=None, strength: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    if emission is not None:
        b.inputs["Emission Color"].default_value = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = strength
    return mat


def _empty(name: str, parent=None, location=(0.0, 0.0, 0.0)):
    ob = bpy.data.objects.new(name, None)
    ob.location = location
    ob.parent = parent
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_symbol(trace_path: Path, parent, navy, gold):
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    pts_all = [pt for piece in data["pieces"].values() for pt in piece]
    xs = [p[0] for p in pts_all]
    ys = [p[1] for p in pts_all]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    scale = SYMBOL_HEIGHT / (max(ys) - min(ys))

    curve = bpy.data.curves.new("A_Symbol_Curve", "CURVE")
    curve.dimensions = "2D"
    curve.fill_mode = "BOTH"
    curve.extrude = 0.09
    curve.bevel_depth = 0.018
    curve.bevel_resolution = 3
    for piece in data["pieces"].values():
        spline = curve.splines.new("POLY")
        spline.points.add(len(piece) - 1)
        for i, (x, y) in enumerate(piece):
            spline.points[i].co = ((x - cx) * scale, -(y - cy) * scale, 0.0, 1.0)
        spline.use_cyclic_u = True
    ob = bpy.data.objects.new("A_Symbol_Metal", curve)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)

    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.view_layer.objects.active
    ob.data.materials.append(navy)
    ob.data.materials.append(gold)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for f in bm.faces:
        f.material_index = 0 if abs(f.normal.z) > 0.95 else 1
    bm.to_mesh(ob.data)
    bm.free()
    for poly in ob.data.polygons:
        poly.use_smooth = True
    ob.parent = parent
    return ob, {"center_px": (cx, cy), "scale": scale}


def build_globe(parent, symbol_frame):
    cx, cy = symbol_frame["center_px"]
    s = symbol_frame["scale"]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=118 * s)
    ob = bpy.context.object
    ob.name = "Globe"
    ob.location = ((845 - cx) * s, -0.05, -(540 - cy) * s)
    for poly in ob.data.polygons:
        poly.use_smooth = True
    mat = bpy.data.materials.new("Globe_Mat")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.02, 0.1, 0.38, 1.0)
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Coat Weight"].default_value = 0.6
    coord = nt.nodes.new("ShaderNodeTexCoord")
    land = nt.nodes.new("ShaderNodeTexNoise")
    land.inputs["Scale"].default_value = 2.2
    land.inputs["Detail"].default_value = 8.0
    land_ramp = nt.nodes.new("ShaderNodeValToRGB")
    land_ramp.color_ramp.elements[0].position = 0.48
    land_ramp.color_ramp.elements[1].position = 0.52
    lights = nt.nodes.new("ShaderNodeTexVoronoi")
    lights.inputs["Scale"].default_value = 90.0
    light_ramp = nt.nodes.new("ShaderNodeValToRGB")
    light_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    light_ramp.color_ramp.elements[1].position = 0.22
    light_ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY"
    tint = nt.nodes.new("ShaderNodeVectorMath")
    tint.operation = "MULTIPLY"
    tint.inputs[1].default_value = (1.0, 0.62, 0.25)
    nt.links.new(coord.outputs["Object"], land.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], lights.inputs["Vector"])
    nt.links.new(land.outputs["Fac"], land_ramp.inputs["Fac"])
    nt.links.new(lights.outputs["Distance"], light_ramp.inputs["Fac"])
    nt.links.new(land_ramp.outputs["Color"], mul.inputs[0])
    nt.links.new(light_ramp.outputs["Color"], mul.inputs[1])
    nt.links.new(mul.outputs["Vector"], tint.inputs[0])
    nt.links.new(tint.outputs["Vector"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 4.0
    ob.data.materials.append(mat)
    ob.parent = parent
    ob.rotation_euler = (0.0, 0.0, 0.0)
    ob.keyframe_insert("rotation_euler", index=2, frame=FRAME_START)
    ob.rotation_euler[2] = math.radians(180)
    ob.keyframe_insert("rotation_euler", index=2, frame=FRAME_END)
    _linear(ob)
    return ob


def build_orbit(parent):
    # Near-horizontal ring tilted toward camera and rolled so its front arc crosses the
    # diagonal gap between a_top and the lower A pieces, as the swoosh does in the poster.
    bpy.ops.mesh.primitive_torus_add(major_radius=1.25, minor_radius=0.045, major_segments=192, minor_segments=16)
    ob = bpy.context.object
    ob.name = "Orbit_Gold"
    ob.location = (0.05, 0.0, -0.02)
    # ZYX applies the animated Z spin first (about the ring's own axis), so the tilt stays fixed.
    ob.rotation_mode = "ZYX"
    ob.rotation_euler = (math.radians(16), math.radians(24), 0.0)
    mat = bpy.data.materials.new("Orbit_Gold_Mat")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1.0, 0.7, 0.3, 1.0)
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.18
    coord = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "RADIAL"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1.0, 0.75, 0.4, 1.0)
    ramp.color_ramp.elements[1].position = 0.18
    ramp.color_ramp.elements[1].color = (0.05, 0.03, 0.0, 1.0)
    nt.links.new(coord.outputs["Object"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 6.0
    ob.data.materials.append(mat)
    ob.parent = parent
    ob.keyframe_insert("rotation_euler", index=2, frame=FRAME_START)
    ob.rotation_euler[2] = math.radians(360)
    ob.keyframe_insert("rotation_euler", index=2, frame=FRAME_END)
    _linear(ob)
    return ob


def build_text(name: str, body: str, font_path: Path, size: float, z: float, parent, mat):
    font = bpy.data.fonts.load(str(font_path), check_existing=True)
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.font = font
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.extrude = 0.012
    curve.bevel_depth = 0.003
    ob = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (0.0, -0.1, z)
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)
    ob.data.materials.append(mat)
    ob.parent = parent
    return ob


def build_background(image_path: Path, cam_rig, cam, distance: float):
    """Camera-locked plate sized to fill the frame at ``distance`` in front of the camera."""
    img = bpy.data.images.load(str(image_path), check_existing=True)
    aspect = img.size[0] / img.size[1]
    width = 2 * distance * math.tan(cam.data.angle_x / 2) * 1.02
    bpy.ops.mesh.primitive_plane_add(size=1)
    ob = bpy.context.object
    ob.name = "BG_Plate"
    ob.scale = (width, width / aspect, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)
    ob.location = (0.0, cam.location.y + distance, 0.0)
    mat = bpy.data.materials.new("BG_Plate_Mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    ob.data.materials.append(mat)
    ob.parent = cam_rig
    strength = em.inputs["Strength"]
    strength.default_value = 0.0
    strength.keyframe_insert("default_value", frame=FRAME_START)
    strength.default_value = 1.0
    strength.keyframe_insert("default_value", frame=FRAME_START + 2 * FPS)
    return ob


def build_lights():
    data = bpy.data.lights.new("LIGHT_Key", "AREA")
    data.energy = 600.0
    data.size = 4.0
    data.color = (1.0, 0.88, 0.7)
    key = bpy.data.objects.new("LIGHT_Key", data)
    bpy.context.scene.collection.objects.link(key)
    key.location = (-3.0, -5.0, 4.0)
    key.rotation_euler = (math.radians(50), 0.0, math.radians(-30))
    for frame, energy in ((2 * FPS, 600.0), (7 * FPS, 1100.0), (12 * FPS, 600.0)):
        data.energy = energy
        data.keyframe_insert("energy", frame=frame)
    rim_data = bpy.data.lights.new("LIGHT_Rim", "AREA")
    rim_data.energy = 400.0
    rim_data.size = 3.0
    rim_data.color = (0.5, 0.7, 1.0)
    rim = bpy.data.objects.new("LIGHT_Rim", rim_data)
    bpy.context.scene.collection.objects.link(rim)
    rim.location = (3.5, 2.0, 3.0)
    rim.rotation_euler = (math.radians(-60), math.radians(30), 0.0)


def _linear(ob) -> None:
    ad = ob.animation_data
    if ad and ad.action:
        for fc in _fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def _fcurves(action):
    if hasattr(action, "fcurves") and action.fcurves is not None:
        try:
            return list(action.fcurves)
        except TypeError:
            pass
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                curves.extend(bag.fcurves)
    return curves


def _pick_engine(scene) -> str:
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    for candidate in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "CYCLES"):
        if candidate in engines:
            scene.render.engine = candidate
            return candidate
    raise SystemExit("no supported render engine")


def build(inputs: dict) -> dict:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.view_settings.view_transform = "AgX"
    engine = _pick_engine(scene)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.002, 0.005, 0.02, 1.0)
    scene.world = world

    cam_rig = _empty("CAM_RIG")
    cam_data = bpy.data.cameras.new("CAM_Main")
    cam_data.lens = 50
    cam = bpy.data.objects.new("CAM_Main", cam_data)
    scene.collection.objects.link(cam)
    cam.parent = cam_rig
    cam.location = (0.0, -9.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.camera = cam

    grp = _empty("GRP_Logo", location=(0.0, 0.0, LOGO_LIFT))
    navy = _principled("A_Navy_Metal", (0.05, 0.16, 0.5), 0.6, 0.18, emission=(0.05, 0.15, 0.5), strength=0.25)
    gold = _principled("A_Gold_Edge", (1.0, 0.62, 0.18), 1.0, 0.2, emission=(1.0, 0.55, 0.12), strength=1.5)
    text_gold = _principled("TXT_Gold", (1.0, 0.6, 0.15), 1.0, 0.25, emission=(1.0, 0.55, 0.12), strength=0.5)
    text_white = _principled("TXT_White", (0.9, 0.92, 1.0), 0.0, 0.4, emission=(0.85, 0.9, 1.0), strength=1.0)

    _, symbol_frame = build_symbol(inputs["paths"]["asia_a_symbol_trace"], grp, navy, gold)
    build_globe(grp, symbol_frame)
    build_orbit(grp)
    build_text("TXT_Company", inputs["company"], inputs["paths"]["font_en"], 0.42, -1.42, grp, text_gold)
    build_text("TXT_Slogan_KO", inputs["slogan"], inputs["paths"]["font_ko"], 0.17, -1.86, grp, text_white)
    build_background(inputs["paths"]["asia_bg_plate"], cam_rig, cam, distance=21.0)
    build_lights()
    return {"engine": engine}


def main() -> None:
    a = _args()
    inputs = resolve_inputs(a.manifest, a.repo_root)
    info = build(inputs)
    a.out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out_blend.resolve()), relative_remap=True)
    print("BUILD_OK", json.dumps({"run_id": inputs["run_id"], **info}))


if __name__ == "__main__":
    main()
