"""Write the PR-C SHA-256 chain: input manifest -> .blend -> PNG sequence -> MP4.

  python -m modules.asia_cinema.pipeline.chain_manifest --run-id <id> --manifest <m> --blend <b> \
      --frames <dir> --video <mp4> --evidence-dir <inbox run dir> --profile final
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .profiles import FRAME_COUNT, NURION_REFERENCE_MP4_SHA256


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sequence_sha256(frame_hashes: list[str]) -> str:
    """Order-sensitive digest over per-frame SHA-256 hex strings."""
    h = hashlib.sha256()
    for fh in frame_hashes:
        h.update(fh.encode("ascii"))
    return h.hexdigest()


def build_chain(
    *,
    run_id: str,
    profile: str,
    manifest_sha256: str,
    blend_sha256: str,
    frame_hashes: list[str],
    video_sha256: str,
    reports: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "apf.asia-cinema-pr-c-run/v1",
        "run_id": run_id,
        "profile": profile,
        "chain": [
            {"step": "input_manifest", "sha256": manifest_sha256},
            {"step": "scene_blend", "sha256": blend_sha256},
            {"step": "png_sequence", "frame_count": len(frame_hashes), "sha256": sequence_sha256(frame_hashes)},
            {"step": "mp4", "sha256": video_sha256},
        ],
        "frame_count_ok": len(frame_hashes) == FRAME_COUNT,
        "nurion_reference_sha256": NURION_REFERENCE_MP4_SHA256,
        "differs_from_nurion_reference": video_sha256.lower() != NURION_REFERENCE_MP4_SHA256,
        "reports": reports,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Write PR-C SHA-256 chain manifest")
    p.add_argument("--run-id", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--blend", type=Path, required=True)
    p.add_argument("--frames", type=Path, required=True)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--evidence-dir", type=Path, required=True)
    a = p.parse_args()

    frames = sorted(a.frames.glob("frame_*.png"))
    reports = {}
    for name in ("input-validation-report.json", "scene-invariants-report.json", f"output-verification-{a.profile}.json"):
        path = a.evidence_dir / name
        if path.is_file():
            reports[name] = {"ok": json.loads(path.read_text(encoding="utf-8")).get("ok"), "sha256": sha256_file(path)}
    chain = build_chain(
        run_id=a.run_id,
        profile=a.profile,
        manifest_sha256=sha256_file(a.manifest),
        blend_sha256=sha256_file(a.blend),
        frame_hashes=[sha256_file(f) for f in frames],
        video_sha256=sha256_file(a.video),
        reports=reports,
    )
    chain["artifacts"] = {
        "manifest_ref": f"<operator-local:{a.manifest.name}>",
        "blend_ref": f"<operator-local:{a.blend.name}>",
        "frames_ref": f"<operator-local:{a.frames.name}/>",
        "video_ref": f"<operator-local:{a.video.name}>",
        "committed": False,
    }
    a.evidence_dir.mkdir(parents=True, exist_ok=True)
    out = a.evidence_dir / f"run.manifest.{a.profile}.json"
    out.write_text(json.dumps(chain, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CHAIN_OK", out.name)


if __name__ == "__main__":
    main()
