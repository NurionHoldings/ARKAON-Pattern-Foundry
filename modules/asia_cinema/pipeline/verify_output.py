"""Verify an encoded ASIA cinema MP4 against the design profile (PR-C).

  python -m modules.asia_cinema.pipeline.verify_output --video <video.mp4> --profile final --report <json>

``check_probe`` is pure so the rules run in CI without ffmpeg.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from .profiles import DURATION_SEC, FPS, FRAME_COUNT, NURION_REFERENCE_MP4_SHA256, PROFILES, Profile

DURATION_TOLERANCE_SEC = 0.05


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def check_probe(
    probe: dict[str, Any],
    profile: Profile,
    *,
    video_sha256: str,
    moov_before_mdat: bool,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    streams = probe.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]

    if len(video) != 1:
        issues.append(_issue("VIDEO_STREAMS", f"expected 1 video stream, found {len(video)}"))
    if audio:
        issues.append(_issue("AUDIO_PRESENT", "audio must be absent"))

    v = video[0] if video else {}
    if (v.get("width"), v.get("height")) != (profile.width, profile.height):
        issues.append(_issue("RESOLUTION", f"expected {profile.width}x{profile.height}"))
    if v.get("codec_name") != "h264":
        issues.append(_issue("CODEC", "codec must be h264"))
    if v.get("pix_fmt") != "yuv420p":
        issues.append(_issue("PIX_FMT", "pix_fmt must be yuv420p"))
    try:
        fps = Fraction(v.get("avg_frame_rate", "0/1"))
    except (ValueError, ZeroDivisionError):
        fps = Fraction(0)
    if fps != FPS:
        issues.append(_issue("FPS", f"frame rate must be {FPS}"))
    frames = v.get("nb_read_frames", v.get("nb_frames"))
    if frames is None or int(frames) != FRAME_COUNT:
        issues.append(_issue("FRAME_COUNT", f"frame count must be {FRAME_COUNT}"))
    duration = float(probe.get("format", {}).get("duration", 0.0))
    if abs(duration - DURATION_SEC) > DURATION_TOLERANCE_SEC:
        issues.append(_issue("DURATION", f"duration must be {DURATION_SEC}s +/- {DURATION_TOLERANCE_SEC}"))
    if not moov_before_mdat:
        issues.append(_issue("FASTSTART", "moov atom must precede mdat (+faststart)"))
    if video_sha256.lower() == NURION_REFERENCE_MP4_SHA256:
        issues.append(_issue("NURION_REFERENCE", "output must not be the NURION reference MP4"))

    return {
        "schema": "apf.asia-cinema-output-verification/v1",
        "profile": profile.name,
        "ok": not issues,
        "issues": issues,
        "checked": {
            "width": v.get("width"),
            "height": v.get("height"),
            "codec": v.get("codec_name"),
            "pix_fmt": v.get("pix_fmt"),
            "fps": str(fps),
            "frame_count": int(frames) if frames is not None else None,
            "duration_sec": round(duration, 3),
            "audio_streams": len(audio),
            "faststart": moov_before_mdat,
            "video_sha256": video_sha256,
            "differs_from_nurion_reference": video_sha256.lower() != NURION_REFERENCE_MP4_SHA256,
        },
    }


def moov_precedes_mdat(path: Path) -> bool:
    """Walk top-level MP4 boxes and report whether ``moov`` comes before ``mdat``."""
    with path.open("rb") as f:
        while True:
            header = f.read(8)
            if len(header) < 8:
                return False
            size = int.from_bytes(header[:4], "big")
            kind = header[4:8]
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:
                size = int.from_bytes(f.read(8), "big")
                f.seek(size - 16, 1)
            elif size == 0:
                return False
            else:
                f.seek(size - 8, 1)


def probe_video(ffprobe: str, path: Path) -> dict[str, Any]:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ASIA cinema MP4")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="final")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--ffprobe", default=shutil.which("ffprobe") or "ffprobe")
    args = parser.parse_args()

    report = check_probe(
        probe_video(args.ffprobe, args.video),
        PROFILES[args.profile],
        video_sha256=hashlib.sha256(args.video.read_bytes()).hexdigest(),
        moov_before_mdat=moov_precedes_mdat(args.video),
    )
    report["video_ref"] = f"<operator-local:{args.video.name}>"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("VERIFY_OK" if report["ok"] else "VERIFY_FAIL", json.dumps(report["issues"], ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
