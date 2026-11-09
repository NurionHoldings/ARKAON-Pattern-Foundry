"""Export a PNG sequence (or selected frames) from the built ASIA cinema .blend (PR-B preview profile).

  blender -b <scene.blend> -P modules/asia_cinema/blender/export_png_sequence.py -- \
      --out-dir <dir> [--width 960 --height 540] [--frames 1,96,200,384]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def _args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--height", type=int, default=540)
    p.add_argument("--frames", default="", help="comma-separated frame numbers; empty = full range")
    return p.parse_args(argv)


def main() -> None:
    a = _args()
    scene = bpy.context.scene
    scene.render.resolution_x = a.width
    scene.render.resolution_y = a.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    a.out_dir.mkdir(parents=True, exist_ok=True)
    out = str(a.out_dir.resolve())
    if a.frames:
        for f in (int(x) for x in a.frames.split(",")):
            scene.frame_set(f)
            scene.render.filepath = f"{out}/frame_{f:04d}.png"
            bpy.ops.render.render(write_still=True)
    else:
        scene.render.filepath = f"{out}/frame_####"
        bpy.ops.render.render(animation=True)
    print("EXPORT_OK", out)


if __name__ == "__main__":
    main()
