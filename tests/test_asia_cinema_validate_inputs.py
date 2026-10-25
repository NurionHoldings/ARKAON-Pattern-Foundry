"""PR-A: ASIA HOLDINGS input bundle validation."""
import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from asia_cinema.validate_inputs import (  # noqa: E402
    InputBundle,
    validate_input_bundle,
)

APPROVED_SLOGAN = "세상을 연결하는 가치, 더 큰 내일을 만듭니다"
APPROVED_SLOGAN_SHA = "e9cc11036d72e2b6216b118d1dce41e3abcf345be7d98cdcffd1b05e16bc19a8"


def _write_file(path: Path, content: bytes) -> str:
    path.write_bytes(content)
    return sha256(content).hexdigest()


def _registration(path: Path, *, approved: bool = True, text: str = APPROVED_SLOGAN) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "approved" if approved else "pending_operator_approval",
                "approved_text": text if approved else None,
                "approved_text_sha256": APPROVED_SLOGAN_SHA if approved else None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _bundle(tmp: Path, reg: Path, slogan: Path, ref: Path, mask: Path, ref_h: str, mask_h: str) -> dict:
    return {
        "schema": "apf.asia-cinema-input-bundle/v1",
        "run_id": "test-run-001",
        "company_name_literal": "ASIA HOLDINGS",
        "assets": [
            {"id": "asia_holdings_reference", "path": str(ref), "sha256": ref_h},
            {"id": "asia_a_symbol_mask", "path": str(mask), "sha256": mask_h},
        ],
        "slogan_ko": {
            "path": str(slogan),
            "sha256": APPROVED_SLOGAN_SHA,
            "registration_path": str(reg),
        },
    }


def test_valid_bundle_passes(tmp_path: Path):
    reg = tmp_path / "reg.json"
    slogan = tmp_path / "slogan.txt"
    ref = tmp_path / "ref.png"
    mask = tmp_path / "mask.png"
    _registration(reg)
    slogan.write_text(APPROVED_SLOGAN, encoding="utf-8")
    ref_h = _write_file(ref, b"reference-bytes")
    mask_h = _write_file(mask, b"mask-bytes")
    report = validate_input_bundle(_bundle(tmp_path, reg, slogan, ref, mask, ref_h, mask_h))
    assert report.ok is True
    assert report.render_allowed is True
    assert report.issues == []


def test_missing_asset_blocked(tmp_path: Path):
    reg = tmp_path / "reg.json"
    slogan = tmp_path / "slogan.txt"
    ref = tmp_path / "ref.png"
    mask = tmp_path / "mask.png"
    _registration(reg)
    slogan.write_text(APPROVED_SLOGAN, encoding="utf-8")
    ref_h = _write_file(ref, b"reference-bytes")
    mask_h = sha256(b"x").hexdigest()
    bundle = _bundle(tmp_path, reg, slogan, ref, mask, ref_h, mask_h)
    report = validate_input_bundle(bundle)
    assert report.ok is False
    assert any(i.code == "FILE_MISSING" for i in report.issues)


def test_hash_mismatch_blocked(tmp_path: Path):
    reg = tmp_path / "reg.json"
    slogan = tmp_path / "slogan.txt"
    ref = tmp_path / "ref.png"
    mask = tmp_path / "mask.png"
    _registration(reg)
    slogan.write_text(APPROVED_SLOGAN, encoding="utf-8")
    _write_file(ref, b"reference-bytes")
    mask_h = _write_file(mask, b"mask-bytes")
    bundle = _bundle(tmp_path, reg, slogan, ref, mask, "0" * 64, mask_h)
    report = validate_input_bundle(bundle)
    assert report.ok is False
    assert any(i.code == "HASH_MISMATCH" for i in report.issues)


def test_unapproved_slogan_blocked(tmp_path: Path):
    reg = tmp_path / "reg.json"
    slogan = tmp_path / "slogan.txt"
    ref = tmp_path / "ref.png"
    mask = tmp_path / "mask.png"
    _registration(reg, approved=False)
    slogan.write_text(APPROVED_SLOGAN, encoding="utf-8")
    ref_h = _write_file(ref, b"reference-bytes")
    mask_h = _write_file(mask, b"mask-bytes")
    report = validate_input_bundle(_bundle(tmp_path, reg, slogan, ref, mask, ref_h, mask_h))
    assert report.ok is False
    assert any(i.code == "SLOGAN_NOT_APPROVED" for i in report.issues)


def test_slogan_text_tamper_blocked(tmp_path: Path):
    reg = tmp_path / "reg.json"
    slogan = tmp_path / "slogan.txt"
    ref = tmp_path / "ref.png"
    mask = tmp_path / "mask.png"
    _registration(reg)
    slogan.write_text("다른 문구", encoding="utf-8")
    ref_h = _write_file(ref, b"reference-bytes")
    mask_h = _write_file(mask, b"mask-bytes")
    bundle = _bundle(tmp_path, reg, slogan, ref, mask, ref_h, mask_h)
    report = validate_input_bundle(bundle)
    assert report.ok is False
    codes = {i.code for i in report.issues}
    assert "SLOGAN_HASH_MISMATCH" in codes or "SLOGAN_TEXT_MISMATCH" in codes


def test_wrong_company_literal_blocked():
    with pytest.raises(Exception):
        InputBundle.model_validate(
            {
                "schema": "apf.asia-cinema-input-bundle/v1",
                "run_id": "x",
                "company_name_literal": "NURION HOLDINGS",
                "assets": [],
                "slogan_ko": {"path": "a", "sha256": "a" * 64, "registration_path": "b"},
            }
        )


def test_public_report_redacts_paths(tmp_path: Path):
    reg = tmp_path / "reg.json"
    slogan = tmp_path / "slogan.txt"
    ref = tmp_path / "ref.png"
    mask = tmp_path / "mask.png"
    _registration(reg)
    slogan.write_text(APPROVED_SLOGAN, encoding="utf-8")
    ref_h = _write_file(ref, b"reference-bytes")
    mask_h = _write_file(mask, b"mask-bytes")
    report = validate_input_bundle(_bundle(tmp_path, reg, slogan, ref, mask, ref_h, mask_h))
    pub = json.dumps(report.to_public_dict())
    assert str(tmp_path) not in pub
    assert "<asset:" in pub
