#!/usr/bin/env python3
"""One-time local ARKAON entrance-film render and optional GitHub upload.
No background service, GPU rental, inbound ports, or secrets in source.
"""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "NurionHoldings/ARKAON-Pattern-Foundry"
TARGET = "assets/entrance/arkaon-awakening.mp4"
APPROVAL = "ARKAON LOCAL RENDER APPROVED"
UPLOAD_APPROVAL = "ARKAON UPLOAD APPROVED"

def confirm(expected):
    if not sys.stdin.isatty():
        raise SystemExit("Interactive administrator confirmation required; no unattended execution")
    if input("관리자 승인 문구 입력 [" + expected + "]: ").strip() != expected:
        raise SystemExit("Approval denied")

def render(image: Path, output: Path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found in PATH. Install FFmpeg first.")
    if not image.is_file():
        raise SystemExit("Approved source image missing: " + str(image))
    if image.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise SystemExit("Unsupported image format")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit("Output already exists; choose another path to avoid overwrite")
    # 8-second, 24fps, 1280x720: gentle zoom, breathing luminance, loopable.
    # Motion is image-based; it is NOT a neural video generation model.
    vf = ("scale=1600:900:force_original_aspect_ratio=increase,"
          "crop=1600:900,zoompan=z='1.02+0.015*sin(on*PI/96)':"
          "x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=192:s=1280x720:fps=24,"
          "eq=brightness=0.015:saturation=1.1,"
          "format=yuv420p")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-loop", "1",
           "-framerate", "24", "-i", str(image), "-vf", vf, "-frames:v", "192",
           "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-movflags", "+faststart", str(output)]
    subprocess.run(cmd, check=True)
    print("Rendered:", output, "bytes:", output.stat().st_size)

def upload(path: Path, branch: str):
    token = os.environ.get("ARKAON_GITHUB_TOKEN")
    if not token:
        raise SystemExit("ARKAON_GITHUB_TOKEN required for GitHub upload")
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise SystemExit("File missing or exceeds 20 MiB upload limit")
    url = "https://api.github.com/repos/" + REPO + "/contents/" + TARGET
    # Only create a new file. Never silently overwrite a deployed asset.
    payload = json.dumps({"message": "Add administrator-approved ARKAON entrance video",
                          "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                          "branch": branch}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT",
             headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
                      "User-Agent": "ARKAON-Local-Video-Uploader"})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit("Upload rejected (HTTP %s): %s" % (exc.code, exc.read(300).decode("utf-8", "replace")))
    print("Uploaded to branch:", branch, "commit:", data["commit"]["sha"])
    print("Review and merge via PR before public deployment.")

def main():
    p = argparse.ArgumentParser(description="Administrator-approved one-time entrance film")
    p.add_argument("--image", type=Path, required=True, help="Approved source image on local PC")
    p.add_argument("--output", type=Path, default=Path("arkaon-awakening.mp4"))
    p.add_argument("--upload", action="store_true", help="Upload to an existing non-main GitHub branch")
    p.add_argument("--branch", default="", help="Existing review branch, not main")
    args = p.parse_args()
    print("Local render only. No rental GPU or server connection.")
    print("Input:", args.image, "Output:", args.output)
    confirm(APPROVAL)
    render(args.image, args.output)
    if args.upload:
        if not args.branch or args.branch in ("main", "master"):
            raise SystemExit("Upload requires an existing non-production review branch")
        print("Upload destination:", REPO, args.branch, TARGET)
        confirm(UPLOAD_APPROVAL)
        upload(args.output, args.branch)

if __name__ == "__main__":
    main()
