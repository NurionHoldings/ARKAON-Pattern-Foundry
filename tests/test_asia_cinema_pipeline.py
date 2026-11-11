"""PR-C: encode command, output verification rules, faststart detection, SHA chain."""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from asia_cinema.pipeline.chain_manifest import build_chain, sequence_sha256
from asia_cinema.pipeline.encode_mp4 import build_ffmpeg_command
from asia_cinema.pipeline.profiles import NURION_REFERENCE_MP4_SHA256, PROFILES
from asia_cinema.pipeline.verify_output import check_probe, moov_precedes_mdat

FINAL = PROFILES["final"]
SHA = "ab" * 32


def _probe(**video_overrides):
    video = {
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "pix_fmt": "yuv420p",
        "avg_frame_rate": "24/1",
        "nb_read_frames": "384",
    }
    video.update(video_overrides)
    return {"streams": [video], "format": {"duration": "16.000000"}}


def _codes(probe, **kw):
    kw.setdefault("video_sha256", SHA)
    kw.setdefault("moov_before_mdat", True)
    return {i["code"] for i in check_probe(probe, FINAL, **kw)["issues"]}


def test_valid_final_output_passes():
    report = check_probe(_probe(), FINAL, video_sha256=SHA, moov_before_mdat=True)
    assert report["ok"] is True
    assert report["checked"]["differs_from_nurion_reference"] is True


def test_wrong_format_blocked():
    codes = _codes(_probe(width=960, height=540, codec_name="hevc", pix_fmt="yuv444p", avg_frame_rate="30/1"))
    assert {"RESOLUTION", "CODEC", "PIX_FMT", "FPS"} <= codes


def test_frame_count_and_duration_blocked():
    probe = _probe(nb_read_frames="383")
    probe["format"]["duration"] = "15.9"
    assert {"FRAME_COUNT", "DURATION"} <= _codes(probe)


def test_audio_and_missing_faststart_blocked():
    probe = _probe()
    probe["streams"].append({"codec_type": "audio", "codec_name": "aac"})
    assert {"AUDIO_PRESENT", "FASTSTART"} <= _codes(probe, moov_before_mdat=False)


def test_nurion_reference_hash_blocked():
    assert "NURION_REFERENCE" in _codes(_probe(), video_sha256=NURION_REFERENCE_MP4_SHA256)


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def test_faststart_detection(tmp_path: Path):
    fast = tmp_path / "fast.mp4"
    fast.write_bytes(_box(b"ftyp", b"isom") + _box(b"moov", b"x" * 16) + _box(b"mdat", b"y" * 32))
    slow = tmp_path / "slow.mp4"
    slow.write_bytes(_box(b"ftyp", b"isom") + _box(b"mdat", b"y" * 32) + _box(b"moov", b"x" * 16))
    assert moov_precedes_mdat(fast) is True
    assert moov_precedes_mdat(slow) is False


def test_ffmpeg_command_matches_design_profile(tmp_path: Path):
    cmd = build_ffmpeg_command("ffmpeg", tmp_path, tmp_path / "out.mp4", FINAL)
    joined = " ".join(cmd)
    for token in ("-c:v libx264", "-crf 18", "-pix_fmt yuv420p", "-movflags +faststart", "-an", "-framerate 24", "-frames:v 384"):
        assert token in joined, token
    assert "scale=1920:1080" in joined


def test_chain_is_order_sensitive_and_flags_frame_count():
    frames = ["a" * 64, "b" * 64]
    assert sequence_sha256(frames) != sequence_sha256(list(reversed(frames)))
    chain = build_chain(
        run_id="r",
        profile="final",
        manifest_sha256="1" * 64,
        blend_sha256="2" * 64,
        frame_hashes=frames,
        video_sha256=SHA,
        reports={},
    )
    assert [s["step"] for s in chain["chain"]] == ["input_manifest", "scene_blend", "png_sequence", "mp4"]
    assert chain["frame_count_ok"] is False
    assert chain["differs_from_nurion_reference"] is True
