import json
from pathlib import Path

import pytest

from apf.owned_platform_connection import (
    ConnectionStatus,
    OwnedPlatformConnectionPolicy,
    OwnedPlatformConnectionRejected,
    build_structural_digest,
    connect_owned_platform,
)

ROOT = Path(__file__).parents[1]


def test_policy_rejects_copy_or_mutation(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "apf.arkaon-owned-platform-connection/v1",
                "read_only": False,
                "copy_source_material": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(OwnedPlatformConnectionRejected, match="read-only structural"):
        OwnedPlatformConnectionPolicy.load(path)


def test_connect_skips_when_repo_path_missing():
    result = connect_owned_platform(foundry_root=ROOT, platform_id="NOGADA_NEWS")
    assert result.status is ConnectionStatus.SKIP
    assert "REPO_PATH" in result.message


def test_structural_digest_captures_layout_without_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('secret should not be exported')", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo", encoding="utf-8")
    digest = build_structural_digest(
        platform_id="NOGADA_NEWS",
        repository=tmp_path,
        policy=OwnedPlatformConnectionPolicy(),
    )
    assert digest.scanned_files >= 2
    assert "src" in digest.top_level_entries
    assert "secret" not in json.dumps(digest.to_document())


def test_connect_structural_when_repo_path_configured(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OWNED_PLATFORM_NOGADA_NEWS_REPO_PATH", str(repo))
    result = connect_owned_platform(foundry_root=ROOT, platform_id="NOGADA_NEWS")
    assert result.status is ConnectionStatus.CONNECTED_READONLY_STRUCTURAL
    assert result.structural_digest is not None
    assert result.structural_digest.digest.startswith("sha256:")
