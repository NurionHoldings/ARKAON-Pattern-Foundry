"""Encode the exported PNG sequence into an H.264 MP4 (PR-C).

  python -m modules.asia_cinema.pipeline.encode_mp4 --frames <dir with frame_0001.png..> \
      --profile final --out <video.mp4>
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from .profiles import FPS, FRAME_COUNT, PROFILES, Profile


def build_ffmpeg_command(ffmpeg: str, frames_dir: Path, out: Path, profile: Profile) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-framerate", str(FPS),
        "-start_number", "1",
        "-i", str(frames_dir / "frame_%04d.png"),
        "-frames:v", str(FRAME_COUNT),
        "-vf", f"scale={profile.width}:{profile.height}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", str(profile.crf),
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-movflags", "+faststart",
        "-an",
        str(out),
    ]


def check_frames(frames_dir: Path) -> None:
    expected = [frames_dir / f"frame_{i:04d}.png" for i in range(1, FRAME_COUNT + 1)]
    missing = [p.name for p in expected if not p.is_file()]
    if missing:
        raise SystemExit(f"missing {len(missing)} frames, first: {missing[0]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Encode ASIA cinema PNG sequence to MP4")
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="final")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    args = parser.parse_args()

    check_frames(args.frames)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_ffmpeg_command(args.ffmpeg, args.frames, args.out, PROFILES[args.profile])
    subprocess.run(cmd, check=True)
    print("ENCODE_OK", args.out.name)


if __name__ == "__main__":
    main()
