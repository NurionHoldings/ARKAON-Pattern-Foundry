from datetime import UTC, datetime
from pathlib import Path

import pytest

from apf.public_surface_observer import PublicSurfaceRejected, observe_public_surface

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FOUNDRY = Path(__file__).resolve().parents[1]


def _write_platform(root: Path, foundry_root: Path) -> None:
    import json
    import subprocess

    (root / "frontend").mkdir(parents=True)
    (root / "frontend" / "app.js").write_text(
        "import r from './r';fetch('/api/demo');export default function Demo(){return 1;}",
        encoding="utf-8",
    )
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "guide.md").write_text("# guide\npublic platform guide text here\n", encoding="utf-8")
    (root / "arkaon.workspace.json").write_text(
        json.dumps(
            {
                "schema_version": "arkaon.workspace/v1",
                "platform_id": "DEMO",
                "foundry_root": str(foundry_root),
                "allowed_analysis_roots": ["frontend", "docs"],
                "forbidden_globs": [".env"],
                "production_change_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=root, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e.com", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=root,
        capture_output=True,
        check=True,
    )


def test_observe_public_surface_returns_structural_digest_only(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    (foundry / "config").mkdir(parents=True)
    (foundry / "config" / "arkaon-public-surface-observation.json").write_text(
        (FOUNDRY / "config" / "arkaon-public-surface-observation.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    platform = tmp_path / "platform"
    _write_platform(platform, foundry)
    report = observe_public_surface(
        platform_id="DEMO",
        platform_path=platform,
        foundry_root=foundry,
        now=NOW,
    )
    assert report.copy_prohibited is True
    assert report.verbatim_storage is False
    assert report.js_structures
    assert len(report.observation_digest) == 64


def test_operational_data_in_visible_text_is_blocked(tmp_path: Path) -> None:
    foundry = tmp_path / "foundry"
    (foundry / "config").mkdir(parents=True)
    (foundry / "config" / "arkaon-public-surface-observation.json").write_text(
        (FOUNDRY / "config" / "arkaon-public-surface-observation.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    platform = tmp_path / "platform"
    _write_platform(platform, foundry)
    (platform / "docs" / "bad.md").write_text("member account handling policy\n", encoding="utf-8")
    with pytest.raises(PublicSurfaceRejected, match="operational or identity"):
        observe_public_surface(
            platform_id="DEMO",
            platform_path=platform,
            foundry_root=foundry,
            now=NOW,
        )
